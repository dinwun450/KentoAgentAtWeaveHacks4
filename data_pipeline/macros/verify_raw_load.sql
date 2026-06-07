{#
    One-off helper: verify seeded tables and row counts in KENTO_DB.RAW.
    Run with: dbt run-operation verify_raw_load
#}
{% macro verify_raw_load() %}
    {% set sql %}
        select 'raw_city_grid' as table_name, count(*) as row_count from KENTO_DB.RAW.raw_city_grid
        union all select 'raw_buildings', count(*) from KENTO_DB.RAW.raw_buildings
        union all select 'raw_roads', count(*) from KENTO_DB.RAW.raw_roads
        union all select 'raw_rubble_locations', count(*) from KENTO_DB.RAW.raw_rubble_locations
        union all select 'raw_survivor_locations', count(*) from KENTO_DB.RAW.raw_survivor_locations
        order by table_name
    {% endset %}
    {% set results = run_query(sql) %}
    {% if execute %}
        {% for row in results.rows %}
            {% do log(row[0] ~ ": " ~ row[1] ~ " rows", info=True) %}
        {% endfor %}
    {% endif %}
{% endmacro %}
