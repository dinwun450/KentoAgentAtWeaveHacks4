with source as (
    select * from {{ ref('raw_buildings') }}
)

select
    building_id,
    building_name,
    x,
    y,
    structure_type,
    damage_state,
    occupancy_risk,
    source
from source
