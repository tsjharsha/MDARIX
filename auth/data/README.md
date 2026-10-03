# Password data

`breached_passwords.txt.gz`: passwords of 12 to 128 characters that appear in public breach corpora, lowercased,
one per line. New passwords that match one (ignoring case) are refused (`auth/service.py`).

Source: SecLists by Daniel Miessler, MIT License (https://github.com/danielmiessler/SecLists):
`Passwords/Common-Credentials/Pwdb_top-1000000.txt` and `100k-most-used-passwords-NCSC.txt`, filtered to 12+
characters. Shorter passwords are already refused by the length rule.

To refresh, download those two files and run:

```bash
cat Pwdb_top-1000000.txt 100k-most-used-passwords-NCSC.txt | tr -d '\r' | tr 'A-Z' 'a-z' \
  | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | awk 'length($0)>=12 && length($0)<=128' \
  | sort -u | gzip -9 -n > auth/data/breached_passwords.txt.gz
```
