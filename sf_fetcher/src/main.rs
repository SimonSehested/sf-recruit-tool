use dotenvy::dotenv;
use serde::Serialize;
use sf_api::{command::Command, SimpleSession};
use std::env;

#[derive(Serialize)]
struct PlayerInfo {
    name: String,
    level: u32,
}

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

    // Først lige et almindeligt update (ikke strengt nødvendigt,
    // men rart at have en frisk GameState)
    let _gs = session.send_command(Command::Update).await?;

    let mut result: Vec<PlayerInfo> = Vec::new();
    let mut page: usize = 0;

    loop {
        // Hent én side Hall of Fame (spillere)
        let gs_page = session
            .send_command(Command::HallOfFamePage { page })
            .await?;

        let players = &gs_page.hall_of_fames.players;

        // Hvis siden er tom, er vi nået forbi sidste side
        if players.is_empty() {
            break;
        }

        for p in players {
            // p.guild == None => ikke i et guild
            if p.level > 100 && p.guild.is_none() {
                result.push(PlayerInfo {
                    name: p.name.clone(),
                    level: p.level,
                });
            }
        }

        page += 1;
    }

    let json = serde_json::to_string_pretty(&result)?;
    println!("{json}");

    Ok(())
}
