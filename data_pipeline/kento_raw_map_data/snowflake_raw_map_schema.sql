create database if not exists KENTO_DB;
create schema if not exists KENTO_DB.RAW;

use database KENTO_DB;
use schema RAW;

create or replace table raw_city_grid (
    map_id string,
    x integer,
    y integer,
    map_symbol string,
    base_terrain string,
    has_building boolean,
    has_road boolean,
    has_rubble boolean,
    has_survivor boolean,
    survivor_id string,
    passable boolean,
    source string,
    loaded_at timestamp default current_timestamp()
);

create or replace table raw_buildings (
    building_id string,
    building_name string,
    x integer,
    y integer,
    structure_type string,
    damage_state string,
    occupancy_risk string,
    source string,
    loaded_at timestamp default current_timestamp()
);

create or replace table raw_roads (
    road_id string,
    x integer,
    y integer,
    road_class string,
    blocked boolean,
    blockage_reason string,
    source string,
    loaded_at timestamp default current_timestamp()
);

create or replace table raw_rubble_locations (
    rubble_id string,
    x integer,
    y integer,
    severity string,
    passable boolean,
    associated_building_id string,
    source string,
    loaded_at timestamp default current_timestamp()
);

create or replace table raw_survivor_locations (
    survivor_id string,
    x integer,
    y integer,
    map_symbol string,
    status string,
    injury_severity string,
    air_supply string,
    visibility string,
    recommended_initial_response string,
    source string,
    loaded_at timestamp default current_timestamp()
);

-- After uploading the CSV files to a Snowflake stage, use COPY INTO, for example:
-- create or replace stage kento_raw_stage;
-- put file://raw_city_grid.csv @kento_raw_stage auto_compress=true;
-- copy into raw_city_grid from @kento_raw_stage/raw_city_grid.csv.gz
-- file_format = (type = csv skip_header = 1 field_optionally_enclosed_by = '"' null_if = ('', 'NULL'));
