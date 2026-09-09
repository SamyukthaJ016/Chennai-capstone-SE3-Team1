package com.team1.trading.api.mapper;

import com.team1.trading.domain.entity.Client;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Result;
import org.apache.ibatis.annotations.Results;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;
import java.util.Optional;

/**
 * Parameterised MyBatis mapper for the clients (accounts) table.
 * All SQL statements use #{...} parameter bindings (OWASP A03 compliant).
 */
@Mapper
public interface ClientMapper {

    @Select("""
            SELECT client_id, account_number, name, email, phone, 
                   created_on, account_state, wallet_balance
            FROM clients
            WHERE client_id = #{clientId}
            """)
    @Results(id = "ClientResultMap", value = {
            @Result(property = "clientId", column = "client_id"),
            @Result(property = "accountNumber", column = "account_number"),
            @Result(property = "name", column = "name"),
            @Result(property = "email", column = "email"),
            @Result(property = "phone", column = "phone"),
            @Result(property = "createdOn", column = "created_on"),
            @Result(property = "accountState", column = "account_state"),
            @Result(property = "walletBalance", column = "wallet_balance")
    })
    Optional<Client> findById(@Param("clientId") Long clientId);

    @Select("""
            SELECT client_id, account_number, name, email, phone, 
                   created_on, account_state, wallet_balance
            FROM clients
            WHERE account_number = #{accountNumber}
            """)
    @Results(id = "ClientResultMapRef")
    Optional<Client> findByAccountNumber(@Param("accountNumber") String accountNumber);

    @Select("""
            SELECT client_id, account_number, name, email, phone, 
                   created_on, account_state, wallet_balance
            FROM clients
            ORDER BY client_id ASC
            """)
    @Results(id = "ClientResultMapRef2")
    List<Client> findAll();

    @Insert("""
            INSERT INTO clients (account_number, name, email, phone, created_on, account_state, wallet_balance, version, updated_on)
            VALUES (#{client.accountNumber}, #{client.name}, #{client.email}, #{client.phone}, 
                    #{client.createdOn}, #{client.accountState}, #{client.walletBalance}, 0, now())
            """)
    @Options(useGeneratedKeys = true, keyProperty = "clientId", keyColumn = "client_id")
    int save(@Param("client") Client client);

    @Update("""
            UPDATE clients
            SET name = #{client.name},
                email = #{client.email},
                phone = #{client.phone},
                updated_on = now()
            WHERE client_id = #{client.clientId}
            """)
    int updateProfile(@Param("client") Client client);

    @Update("""
            UPDATE clients
            SET account_state = #{accountState},
                updated_on = now()
            WHERE client_id = #{clientId}
            """)
    int updateAccountState(@Param("clientId") Long clientId, @Param("accountState") String accountState);
}