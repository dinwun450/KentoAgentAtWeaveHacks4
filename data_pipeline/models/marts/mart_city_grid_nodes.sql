-- Matured semantic view of the disaster grid: one row per cell with a single
-- derived node_type and passability. Hydrates Redis grid:node:x:y.

with grid as (
    select * from {{ ref('stg_city_grid') }}
),

survivors as (
    select survivor_id, status as survivor_status
    from {{ ref('stg_survivor_locations') }}
),

buildings as (
    select x, y, max(building_id) as building_id
    from {{ ref('stg_buildings') }}
    group by x, y
),

roads as (
    select x, y, max(road_id) as road_id
    from {{ ref('stg_roads') }}
    group by x, y
),

rubble as (
    select x, y, max(severity) as rubble_severity
    from {{ ref('stg_rubble_locations') }}
    group by x, y
)

select
    g.x::varchar || '-' || g.y::varchar as node_key,
    g.map_id,
    g.x,
    g.y,
    g.base_terrain,
    case
        when g.has_survivor and lower(s.survivor_status) like '%trapped%' then 'survivor_trapped'
        when g.has_survivor                                              then 'survivor_visible'
        when g.has_rubble                                               then 'rubble'
        when g.has_building                                             then 'building'
        when g.has_road                                                 then 'road'
        else 'clear'
    end as node_type,
    g.passable,
    g.has_building,
    g.has_road,
    g.has_rubble,
    g.has_survivor,
    g.survivor_id,
    b.building_id,
    r.road_id,
    rb.rubble_severity
from grid g
left join survivors s on g.survivor_id = s.survivor_id
left join buildings b on g.x = b.x and g.y = b.y
left join roads r on g.x = r.x and g.y = r.y
left join rubble rb on g.x = rb.x and g.y = rb.y
