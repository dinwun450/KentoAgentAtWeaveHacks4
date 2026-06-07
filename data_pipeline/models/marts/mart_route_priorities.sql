-- Road segments summarized for route planning / clearance. Arterial routes with
-- any blockage are most urgent to clear. Feeds the RoutePlanningAgent.

with roads as (
    select * from {{ ref('stg_roads') }}
),

agg as (
    select
        road_id,
        max(road_class)   as road_class,
        count(*)          as total_cells,
        count_if(blocked) as blocked_cells
    from roads
    group by road_id
)

select
    road_id,
    road_class,
    total_cells,
    blocked_cells,
    round(100.0 * blocked_cells / nullif(total_cells, 0), 1) as pct_blocked,
    (blocked_cells > 0) as any_blocked,
    case
        when blocked_cells = 0            then 'none'
        when road_class = 'arterial'      then 'critical'
        when blocked_cells = total_cells  then 'high'
        else 'medium'
    end as clearance_priority
from agg
order by
    case
        when blocked_cells = 0       then 3
        when road_class = 'arterial' then 0
        else 1
    end,
    pct_blocked desc
