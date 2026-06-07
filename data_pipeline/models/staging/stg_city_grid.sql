with source as (
    select * from {{ ref('raw_city_grid') }}
)

select
    map_id,
    x,
    y,
    map_symbol,
    base_terrain,
    has_building,
    has_road,
    has_rubble,
    has_survivor,
    nullif(survivor_id, '') as survivor_id,
    passable,
    source
from source
