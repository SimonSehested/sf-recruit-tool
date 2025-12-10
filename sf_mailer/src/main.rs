use dotenvy::dotenv;
use sf_api::{command::Command, SimpleSession};
use std::{env, error::Error};

async fn send_sf_message(to: &str, body: &str) -> Result<(), Box<dyn Error>> {
    dotenv().ok();

    let username = env::var("SF_USERNAME")
        .expect("SF_USERNAME mangler (din S&F account e-mail)");
    let password = env::var("SF_PASSWORD")
        .expect("SF_PASSWORD mangler (dit S&F account password)");

    let sessions = SimpleSession::login_sf_account(&username, &password).await?;
    let mut session = sessions
        .into_iter()
        .next()
        .ok_or("Ingen karakterer fundet på denne S&F account")?;

    // Frisk gamestate
    let _gs = session.send_command(Command::Update).await?;

    // Selve beskeden
    session
        .send_command(Command::SendMessage {
            to: to.to_string(),
            msg: body.to_string(),
        })
        .await?;

    Ok(())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let mut args = env::args().skip(1);

    // brug: sf_mailer <navn> <besked>
    let to = args.next().expect("Brug: sf_mailer <navn> <besked>");
    // Resten af argumenterne slås sammen til beskeden, så du kan have mellemrum
    let msg: String = args.collect::<Vec<_>>().join(" ");

    send_sf_message(&to, &msg).await
}
