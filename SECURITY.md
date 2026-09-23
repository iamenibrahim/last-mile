# Security policy

## Report a vulnerability

Do not file public issues containing citizen data, credentials, or unredacted alert-provider logs. Send a minimal reproduction to the repository owner through the private channel listed in the project page.

## Sensitive-data rules

- Never add Azure keys or signing material to the repository.
- Never log `/api/navigate` request bodies.
- Never accept identity-document uploads in this application.
- Never treat a provider confidence score as an eligibility decision.
- Never present an allowlisted domain as proof that a message is authentic.
- Never claim the app verifies an NWS digital signature.

## Production checklist

- Use managed identity and Key Vault.
- Disable local HMAC demo keys.
- Restrict CORS to the deployed front-end origin.
- Add rate limits and request-size limits at the edge.
- Pin outbound hosts and use private networking where feasible.
- Review every program record and source timestamp before deployment.
- Test screen-reader, keyboard-only, reduced-motion, and 200% zoom behavior.

