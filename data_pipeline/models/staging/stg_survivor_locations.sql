with source as (
    select * from {{ ref('raw_survivor_locations') }}
)

select
    survivor_id,
    x,
    y,
    map_symbol,
    status,
    injury_severity,
    nullif(air_supply, '') as air_supply,
    visibility,
    recommended_initial_response,
    source
from source
