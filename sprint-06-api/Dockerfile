# ---- Stage 1: build ---------------------------------------------------------
# Maven + full JDK 21. Resolved dependencies are cached before the source is
# copied, so changing a source file does not invalidate the dependency layer.
#
# The Sprint 5 domain engine is a Maven artifact, not source: a pre-built jar
# is provided in ./lib (see lib/README.md) and installed into the Maven
# repository before dependency resolution and the build.
FROM maven:3.9.16-eclipse-temurin-21 AS build
WORKDIR /src

COPY pom.xml .
COPY lib/domain-engine-1.0-SNAPSHOT.jar /lib/domain-engine-1.0-SNAPSHOT.jar
RUN mvn -B -q install:install-file \
    -Dfile=/lib/domain-engine-1.0-SNAPSHOT.jar \
    -DgroupId=com.team1.trading \
    -DartifactId=domain-engine \
    -Dversion=1.0-SNAPSHOT \
    -Dpackaging=jar

RUN mvn -B -q dependency:go-offline

COPY src ./src
RUN mvn -B -q clean package -DskipTests

# ---- Stage 2: runtime -------------------------------------------------------
# Java 21 JRE only: neither Maven nor a JDK. Runs as a non-root user so nothing
# build-time (compiler, dependency cache, sources) is present at runtime.
FROM eclipse-temurin:21-jre
WORKDIR /app

RUN useradd --system --uid 10001 --shell /usr/sbin/nologin app
USER app

COPY --from=build /src/target/sprint-06-api-0.0.1-SNAPSHOT.jar /app/app.jar

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=12 \
  CMD curl -fsS http://localhost:8080/actuator/health || exit 1

ENTRYPOINT ["java", "-jar", "/app/app.jar"]