package com.team1.trading.api;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = "spring.datasource.url=jdbc:h2:mem:bootctx;DB_CLOSE_DELAY=-1")
class Sprint06ApiApplicationTests {

    @Test
    void contextLoads() {
    }

}
