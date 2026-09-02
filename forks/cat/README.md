# `.mini-cat` — Product catalogue entries

**Prefix:** `cat`  **Version:** 1  **Parent:** —  **Domain:** e-commerce

Catalogue rows with price, currency, stock, tags and optional rating.

## Record layout

```
sku:str | name:str | category:str | price:float[0..] | currency:enum{USD|PEN|EUR} | stock:int[0..] | tags:list<str>[0..10] | rating:float[0..5]?
```

| # | field | type | notes |
|---|---|---|---|
| 1 | `sku` | `str` | core |
| 2 | `name` | `str` | core |
| 3 | `category` | `str` | core |
| 4 | `price` | `float[0..]` | core |
| 5 | `currency` | `enum{USD|PEN|EUR}` | core |
| 6 | `stock` | `int[0..]` | core |
| 7 | `tags` | `list<str>[0..10]` | core |
| 8 | `rating` | `float[0..5]?` | core; optional |

## Header keys

| key | type | required | description |
|---|---|---|---|
| `d` | `str` | no | generation date YYYYMMDD |
| `store` | `str` | no |  |
| `cur` | `str` | no | default currency |
| `n` | `int` | yes | number of records |
| `v` | `int` | no | contract version |

## Example

```
cat|n=12|d=20260603|store=campus-shop|cur=USD
SKU-1001|Wireless headset|audio|89.9|USD|120|bluetooth,noise-cancelling|4.5
SKU-1002|USB-C hub 7-in-1|accessories|39.99|USD|300|usb-c,hdmi|4.2
…
```

## Fixtures

`fixtures/valid.mini` ↔ `fixtures/canonical.json` (round-trip), `fixtures/escaping.mini` ↔ `fixtures/escaping.json`, and the negative cases `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`.

## Prompt block

Generate the transferable specification with `mini prompt cat`.
