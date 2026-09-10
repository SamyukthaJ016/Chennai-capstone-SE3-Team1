# Provided artifacts (built outside this project)

`domain-engine-1.0-SNAPSHOT.jar` — the Sprint 5 domain engine. Not built here:
generate it from `sprint-05-domain-engine` and place it in this folder so the
Docker build can install it.

```bash
mvn -f sprint-05-domain-engine/pom.xml clean install
cp sprint-05-domain-engine/target/domain-engine-1.0-SNAPSHOT.jar sprint-06-api/lib/
```

Expected file: `domain-engine-1.0-SNAPSHOT.jar` (the Dockerfile
copies this exact name and `pom.xml` depends on
`com.team1.trading:domain-engine:1.0-SNAPSHOT`).