with source as (
    select * from {{ ref('raw_rubble_locations') }}
)

select
    rubble_id,
    x,
    y,
    severity,
    passable,
    nullif(associated_building_id, '') as associated_building_id,
    source
from source
