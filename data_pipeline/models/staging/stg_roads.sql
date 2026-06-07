with source as (
    select * from {{ ref('raw_roads') }}
)

select
    road_id,
    x,
    y,
    road_class,
    blocked,
    nullif(blockage_reason, '') as blockage_reason,
    source
from source
