# Strategy Engine V2 Design

## Objective

Replace fixed weighted scoring with configurable strategy models.

## Strategy Structure

Each strategy contains:

-   factor weights
-   market overlay
-   filters
-   ranking rules
-   risk rules

## Strategies

### balanced_v2

quality 30% valuation 20% momentum 20% volatility 15% liquidity 10%
dividend 5%

### growth_momentum_v2

momentum 35% quality 20% valuation 20% liquidity 15% volatility 10%

### value_defensive_v2

valuation 35% quality 30% dividend 20% volatility 15%

### turning_point_v2

Two stage model:

Stage 1: - oversold detection - volume recovery - fundamental filter

Stage 2: - quality - valuation - momentum scoring
