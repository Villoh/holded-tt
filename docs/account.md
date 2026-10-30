# Account commands

Sign in, check the saved session and look up your workplace and profile.

## `holded-tt login`
Authenticates with Holded interactively and saves the session locally.

The command always prompts for your email and password. If Holded requires two-factor authentication, it then prompts for the 2FA code and completes the login flow.

```bash
holded-tt login
```

## `holded-tt session`
Shows the saved session status, validation mode, and when it was last refreshed. By default it validates the saved cookies live against Holded using `/internal/real-time/discover`.

```bash
holded-tt session
holded-tt session --live
holded-tt session --offline
```

`--live` checks the current session against Holded. `--offline` only inspects the locally saved cookies and timestamp.

## `holded-tt workplaces`
Lists all workplace IDs and names available in your account. Use the ID to configure your default workplace.

```bash
holded-tt workplaces
```

## `holded-tt employee`
Shows your merged employee profile by combining the Holded employee and personal-info endpoints.

```bash
holded-tt employee
```

## `holded-tt organization`
Lists organization employees from the Holded Teamzone organization endpoint.

```bash
holded-tt organization
```

## Session troubleshooting

- Run `holded-tt session` to inspect whether a saved session exists, whether live validation succeeds, and when it was last refreshed.
- Use `holded-tt session --offline` if you only want to inspect the locally saved cookies and timestamp.
- If commands report that no saved session is available or that the session is expired, run `holded-tt login` again.
- If `holded-tt login` fails during 2FA, verify the code and try again.
