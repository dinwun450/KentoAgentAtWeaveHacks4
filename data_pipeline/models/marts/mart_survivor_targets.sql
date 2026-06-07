-- Survivors ranked for rescue. Priority is AIR SUPPLY FIRST (suffocation risk
-- is time-critical), then INJURY SEVERITY. Feeds the TriageAgent and the
-- live:survivor:id hot-memory records.

with survivors as (
    select * from {{ ref('stg_survivor_locations') }}
),

scored as (
    select
        survivor_id,
        x,
        y,
        status,
        injury_severity,
        air_supply,
        visibility,
        recommended_initial_response,
        case lower(coalesce(air_supply, ''))
            when 'critical' then 100
            when 'low'      then 90
            when 'limited'  then 80
            when 'stable'   then 40
            else 10  -- visible survivors with no reported air constraint
        end as air_priority,
        case lower(coalesce(injury_severity, ''))
            when 'critical' then 50
            when 'severe'   then 40
            when 'moderate' then 30
            when 'minor'    then 10
            else 0
        end as injury_priority
    from survivors
)

select
    survivor_id,
    x,
    y,
    status,
    injury_severity,
    air_supply,
    visibility,
    recommended_initial_response,
    air_priority,
    injury_priority,
    (air_priority * 100) + injury_priority as priority_score,
    row_number() over (
        order by (air_priority * 100) + injury_priority desc, survivor_id
    ) as priority_rank
from scored
