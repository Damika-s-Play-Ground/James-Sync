# Secure runtime backup

The live runtime was snapshotted read-only and encrypted before leaving
Donely.

- S3 bucket: james-donely-freeze-255530395844-20260919
- Object: donely/20260919/james-runtime-freeze.bundle.tgz
- Object size: 208,083,107 bytes
- Bundle SHA-256:
  dc9981bd04ed05069e0b26e63fdc87e31136d95fc1be1ae94788b9dfc4810683
- S3 controls: public access blocked, AES-256 server-side encryption, versioning enabled.

The bundle contains:

- a gzip archive of Hermes/OpenClaw configuration, the WhatsApp store,
  session/log/history data, media/cache data, source workspace, and database
  snapshots;
- runtime.tar.gz.enc, encrypted with AES-256-CBC, PBKDF2, and 200,000
  iterations;
- aes.key.enc, where the AES key is wrapped with the local 3072-bit RSA
  recipient public key;
- a manifest with component checksums.

The RSA private key is not in Git or S3. It is held locally at:

C:\Users\Damika.Nanayakkara\Documents\James\james-freeze-keys\runtime-recipient-private.pem

Keep that key protected. To restore, unpack the bundle, decrypt aes.key.enc
with the private key using RSA-OAEP/SHA-256, then decrypt runtime.tar.gz.enc
with AES-256-CBC/PBKDF2. Never place the decrypted archive or extracted
runtime data in this Git repository.

A second encrypted copy is stored locally outside the repo under
james-runtime-backups\20260919\.
