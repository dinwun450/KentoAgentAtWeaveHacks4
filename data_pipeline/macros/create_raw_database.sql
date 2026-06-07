{#
    One-off helper: ensure the KENTO_DB database exists before seeding.
    dbt auto-creates schemas but not databases.
    Run with: dbt run-operation create_raw_database
#}
{% macro create_raw_database() %}
    {% set sql %}
        create database if not exists KENTO_DB;
        create schema if not exists KENTO_DB.RAW;
    {% endset %}
    {% do run_query(sql) %}
    {% do log("Ensured KENTO_DB.RAW exists.", info=True) %}
{% endmacro %}
