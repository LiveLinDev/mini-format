use std::io::{self, Read};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut text = String::new();
    io::stdin().read_to_string(&mut text)?;
    let output = match std::env::args().nth(1).as_deref() {
        Some("encode") => hedl::canonicalize(&hedl::from_json(&text)?)?,
        Some("decode") => hedl::to_json(&hedl::parse(&text)?)?,
        _ => return Err("Expected encode or decode".into()),
    };
    println!("{output}");
    Ok(())
}
