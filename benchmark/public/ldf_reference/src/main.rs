use ldf_data::Value;
use ldf_data::input::parse_json_value;
use std::io::{self, Read};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = Vec::new();
    io::stdin().read_to_end(&mut input)?;
    let records = match parse_json_value(&mut input, Default::default())? {
        Value::Array(rows) => rows,
        record @ Value::Object(_) => vec![record],
        _ => return Err("expected a list of records or an object".into()),
    };
    let mut options = ldf::Options::default();
    options.hoist = match std::env::args().nth(1).as_deref() {
        Some("regular") => false,
        Some("hoist") => true,
        _ => return Err("expected regular or hoist".into()),
    };
    let encoded = ldf::encode_with(&records, &options);
    let decoded = ldf::decode(&encoded)?;
    if decoded.len() != records.len()
        || !records
            .iter()
            .zip(&decoded)
            .all(|(a, b)| a.semantic_eq_unordered(b))
    {
        return Err("the official decoder changed the source records".into());
    }
    print!("{encoded}");
    Ok(())
}
