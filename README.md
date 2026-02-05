# url-shortner

1. Requirements Analysis
Functional Requirements
------------------------------------------------------------------------------
    Shorten URLs: Generate unique short URLs for given long URLs

    Redirect: Redirect short URLs to original long URLs with minimal latency

    Custom Aliases: Support user-defined custom short URLs

    Expiration: URLs expire after configurable TTL

    Analytics: Track clicks, geographic data, referrers (non-real-time acceptable)

    Deduplication: Same long URL → same short URL (1-to-1 mapping)

Non-Functional Requirements
--------------------------------------------------------------------------------
    High Availability: 99.9%+ uptime (AP from CAP theorem)

    Low Latency: <100ms for redirects, <500ms for creation

    Scalability: Handle billions of URLs, millions of requests/second

    Durability: URLs persist for years

    Security: Prevent malicious URLs, spam protection, non-predictable short codes

    Read-Heavy: 100:1 read-to-write ratio typical

Capacity Estimation
-------------------------------------------------------------------------------
assume 1B urls per month, 1 KB per record 

storage
1B * 12 months * 3 Year * 1KB = 36 B

HA 3 * 36 TB = 108 TB


Traffic
writes 1B /30/24/60/60 ~ 400TPS, peak 2000TPS
reads 100 * 400 = 40000 TPS, peak 200000TPS


2. High Level Design

