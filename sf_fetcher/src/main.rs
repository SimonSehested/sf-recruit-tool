use dotenvy::dotenv;
use serde::Serialize;
use sf_api::{command::Command, SimpleSession};
use std::env;

#[derive(Serialize)]
struct PlayerInfo {
    name: String,
    level: u32,
}

// ~5000 spillere / 50–51 pr. side ≈ 100 sider
const MAX_PAGES: usize = 100;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    dotenv().ok();

    let username = env::var("SF_USERNAME")
        .expect("SF_USERNAME mangler (din S&F account e-mail)");
    let password = env::var("SF_PASSWORD")
        .expect("SF_PASSWORD mangler (dit S&F account password)");

    // Log ind på SF account (SSO)
    let sessions = SimpleSession::login_sf_account(&username, &password).await?;

    let mut session = sessions
        .into_iter()
        .next()
        .ok_or("Ingen karakterer fundet på denne S&F account")?;

    // Lige et almindeligt update først
    let _gs = session.send_command(Command::Update).await?;

    let mut result: Vec<PlayerInfo> = Vec::new();

    for page in 0..MAX_PAGES {
        eprintln!("Henter Hall of Fame side {page}...");

        // Håndtér fejl pænt (ingen panik / crash)
        let gs_page = match session
            .send_command(Command::HallOfFamePage { page })
            .await
        {
            Ok(gs_page) => gs_page,
            Err(e) => {
                eprintln!("Fejl ved hentning af Hall of Fame side {page}: {e}");
                // typisk her du så 'ServerError(\"server not available\")' før
                // nu stopper vi bare og bruger det, vi allerede har
                break;
            }
        };

        let players = &gs_page.hall_of_fames.players;
        eprintln!("Side {page}: fik {} spillere", players.len());

        // Tom side = vi er forbi sidste side → stop
        if players.is_empty() {
            break;
        }

        for p in players {
            // 🔥 Level-filter er droppet – vi stoler på at alle i top 5000 er > 100
            // stadig kun spillere uden guild (rekrutterbare)
            if p.guild.is_none() {
                result.push(PlayerInfo {
                    name: p.name.clone(),
                    level: p.level,
                });
            }
        }
    }

    let json = serde_json::to_string_pretty(&result)?;
    println!("{json}");

    Ok(())
}
