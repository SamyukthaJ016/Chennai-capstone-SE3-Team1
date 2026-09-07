package com.team1.trading.api.mapper;

import com.team1.trading.domain.entity.Client;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;
import java.util.Optional;

@Mapper
public interface ClientMapper {

    @Select("""
            SELECT client_id, account_number, name, email, phone, created_on, account_state, wallet_balance
            FROM clients
            WHERE client_id = #{clientId}
            """)
    Optional<Client> findById(@Param("clientId") Long clientId);

    @Select("""
            SELECT client_id, account_number, name, email, phone, created_on, account_state, wallet_balance
            FROM clients
            ORDER BY client_id
            """)
    List<Client> findAll();

    @Select("""
            SELECT client_id, account_number, name, email, phone, created_on, account_state, wallet_balance
            FROM clients
            WHERE account_number = #{accountNumber}
            """)
    Optional<Client> findByAccountNumber(@Param("accountNumber") String accountNumber);

    @Insert("""
            INSERT INTO clients (account_number, name, email, phone, created_on, account_state, wallet_balance)
            VALUES (#{accountNumber}, #{name}, #{email}, #{phone}, #{createdOn}, #{accountState}, #{walletBalance})
            """)
    int save(Client client);

    @Update("""
            UPDATE clients
            SET name = #{name}, email = #{email}, phone = #{phone}
            WHERE client_id = #{clientId}
            """)
    int updateProfile(Client client);

    @Update("""
            UPDATE clients
            SET account_state = #{accountState}
            WHERE client_id = #{clientId}
            """)
    int updateAccountState(@Param("clientId") Long clientId, @Param("accountState") String accountState);
}
