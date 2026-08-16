"""Seed the photobooth-route campaign's 45 westside venue leads + manual drafts.

One-off (2026-08-16), idempotent — re-running skips existing rows. The campaign row
must exist first (scripts.sync_campaigns picks up backend/campaigns/photobooth-route/).

Leads are venues, not people: linkedin_url holds the venue's Instagram profile URL
(the unique key + the tap-to-open link in /drafts), email_status stays NULL so the
email sender's deliverability gate can never match them. Drafts use channels
'manual_ig' / 'manual_email', which no sender query matches — the operator sends
every message personally from the dashboard via Copy + Mark sent.

    uv run python -m scripts.seed_photobooth_route
"""

from __future__ import annotations

import psycopg
from psycopg.types.json import Jsonb

from config import require

T1, T2, T3 = "Tier 1 target", "Tier 2 target", "Tier 3 target"
SIG = {T1: 5, T2: 3, T3: 2}

# (name, area, tier, ig_handle, email|None, subject|None, vibe, hook, busy, message)
VENUES: list[tuple] = [
    ("The Gaslite", "Santa Monica · Wilshire", T1, "thegaslite", None, None,
     "Shoebox karaoke dive since 1962, free popcorn, zero pretension",
     "Karaoke 365 days a year, from 8am on weekends", "Hour+ waits, packed weekends",
     "Karaoke 365 days a year with an hour wait on weekends — and the only thing anyone takes home is a hangover. I'm starting a small photo booth route on the westside: vintage-style booth, zero cost to the bar, I handle install and upkeep, you take a cut of every strip. Feels made for the moment right after someone nails their song. Is that something you decide in-house, or the owner's call?"),
    ("Tavern on Main", "Santa Monica · Main St", T1, "tavernonmainsm", "info@tavernonmainsm.com", "photo booth for the Tavern?",
     "Neighborhood sports bar, 20+ TVs, karaoke and DJ nights",
     "Main St's only pool table; Most Loved Happy Hour 2025; same owners as Circle Bar + Hinano",
     "Game-day + karaoke crowds to 2am",
     "Main Street's only pool table plus karaoke nights — you're already where groups end up after dark. I'm starting a small route of coin-op photo booths in westside bars: costs the bar nothing, I install and maintain it, the house gets a share of every vend, and the strips print with your logo. Does that kind of decision go through you or ownership?\n\n— Chance"),
    ("Circle Bar", "Santa Monica · Main St", T1, "circlebarsm", "info@circlebar-sm.com", None,
     "Red-lit 1949 dive reborn May 2026 as a late-night DJ den",
     "The Halo elevated DJ booth + 8K laser rig; same owners as Tavern on Main + Hinano",
     "Nightly DJs Thu-Sat to 2am",
     "The Halo and an 8K laser rig — you clearly rebuilt the room for nights people want to remember. I'm starting a small photo booth route on the westside: vintage-style machine, free to the venue, I service everything, the bar takes a cut of each strip. Red-lit strips from Circle Bar would end up on a lot of fridges. Who's the right person to run that by?"),
    ("Hinano Cafe", "Venice · Washington Blvd", T1, "hinanovenice", "info@hinanocafevenice.com", None,
     "Sawdust-floor beach dive since 1962, Jim Morrison's local",
     "Bands Fri/Sat/Sun 5pm; legendary charred-patty cheeseburger; same owners as Circle Bar + Tavern on Main",
     "Bands 3 nights/wk + NFL Sundays",
     "Bands three nights a week, sawdust on the floor, sixty years of stories — and no photo evidence unless someone remembers their phone. I'm starting a small photo booth route on the westside: old-school booth, free to you, I keep it running, the bar takes a cut of every strip. Is there a corner by the pool tables that could take one?"),
    ("Ye Olde King's Head", "Santa Monica · downtown", T1, "yeoldekingshead", "info@yeoldekingshead.com", "a photo booth that pays the pub",
     "British pub institution since 1974, a block from the beach",
     "HOT LEAD: rented a photo booth for their 50th anniversary party (2024)",
     "Promenade tourist flow, 1900+ Yelp reviews",
     "You rented a photo booth for the 50th anniversary — I'd like to put one in permanently that pays the pub instead of costing it. I'm starting a small route of vintage-style booths in westside bars: free to the venue, I handle install and upkeep, King's Head takes a cut of every strip, prints carry your branding. Who's the right person there to run this by?\n\n— Chance"),
    ("Townhouse & Del Monte Speakeasy", "Venice · Windward Ave", T1, "townhousevenice", "info@townhousevenice.com", "photo booth for the Del Monte?",
     "Oldest bar in Venice (1915); Prohibition speakeasy basement",
     "Real Prohibition speakeasy (liquor via dumbwaiter); live jazz/comedy/burlesque nightly",
     "Weekend lines at the bar, ticketed shows",
     "A speakeasy that ran liquor down a dumbwaiter deserves analog souvenirs. I'm starting a small photo booth route on the westside — vintage-style machine, no cost to the venue, I service it, Townhouse takes a cut of every strip. The jazz and burlesque crowds downstairs would keep it busy. Who's the right person to talk to about the space?\n\n— Chance"),
    ("The Brig", "Venice · Abbot Kinney", T1, "thebrigvenice", "info@thebrig.com", None,
     "Abbot Kinney's last true dive (~70 years), retro remodel, patio",
     "Famous for great mojitos at a shot-and-beer dive",
     "Saturday crowds spill onto the patio",
     "Mojitos at a shot-and-beer dive is already a story people tell — the photo strip is the proof that should go with it. I'm starting a photo booth route on the westside: vintage-style machine, costs the Brig nothing, I handle everything, you take a cut of each strip. Your call, or the owner's?"),
    ("Roosterfish", "Venice · Abbot Kinney", T1, "roosterfish_venice", "RoosterfishAK@gmail.com", "photo booth idea for Roosterfish",
     "Landmark LGBTQ+ bar since 1979, revived after 2016 closure",
     "18-cocktail craft list; weekend disco/dance nights to 2am",
     "Fri-Sun to 2am, weekend dance nights",
     "Forty-plus years of history, back from a two-year closure, disco nights until 2 — Roosterfish strips would be instant keepsakes. I'm starting a small route of vintage-style photo booths in westside bars: free to the venue, I maintain it, the bar shares in every vend, prints carry your branding. Is that something you all decide in-house?\n\n— Chance"),
    ("Prince O' Whales", "Playa del Rey · Culver Blvd", T1, "princeowhales", "prince.o.whales.management@gmail.com", "photo booth for PoW?",
     "Beachside neighborhood dive since 1955; two bars, two patios",
     "Karaoke Tue/Thu 10pm (Thu hosted by Kiki); ping pong + darts in-bar",
     "Popular weekends, late karaoke crowds",
     "Karaoke Tuesdays and Thursdays with Kiki, ping pong in the bar — PoW is already built for groups who want proof of the night. I'm starting a small coin-op photo booth route on the westside: the booth costs you nothing, I install and service it, the bar takes a cut of every strip. Is there a corner that could fit a phone-booth footprint?\n\n— Chance"),
    ("Q's Billiard Club", "Brentwood · Wilshire", T1, "qsbilliards", "contact@qsbilliardclub.com", "photo booth for Q's?",
     "Two-story pool-hall sports bar since 1989, DJ nightly",
     "10 red-felt tables; beer pong Sundays; trivia Wednesdays",
     "Hour+ pool waits, 'entirely too crowded' weekends",
     "Hour-long waits for a red-felt table on weekends — that's a room full of people looking for something to do between games. I'm starting a photo booth route on the westside: vintage-style booth at zero cost to the venue, I run and service the machine, Q's takes a share of every strip. Who's the right person to run this by?\n\n— Chance"),
    ("The Nickel Mine", "West LA · Santa Monica Blvd", T1, "nickelmine", "thenickelmine@gmail.com", "photo booth for the Nickel Mine?",
     "Big independent sports bar (2016), 'well-kept frat house' energy",
     "Hidden speakeasy-style back room (~30 ppl); board games; 24 rotating taps",
     "Packed-to-the-gills game days",
     "Packed-to-the-gills game days plus a hidden room in back — that's the exact crowd photo booths were built for. I'm starting a small booth route on the westside: vintage-style machine, free to the bar, I handle upkeep, you get a cut of each vend. Does that decision sit with you or ownership?\n\n— Chance"),
    ("The Garage on Motor Ave", "Palms · Motor Ave", T1, "garageonmotor", "info@garageonmotor.com", "photo booth for the Garage?",
     "Palms' sports bar 10+ years; 30+ TVs, fight nights",
     "Hidden back bar 'Motor Club' Wed-Sat to 2am; karaoke Fri/Sat 10pm; UFC/boxing PPVs",
     "PPV fight nights pack the room",
     "Fight nights, Friday and Saturday karaoke, and the Motor Club in back — you've got three different crowds a week who'd feed a photo booth. I'm starting a small route of vintage-style booths: free to the venue, I service everything, the Garage takes a cut per strip. Is that your call, or the owner's?\n\n— Chance"),
    ("Harvelle's", "Santa Monica · 4th St", T1, "harvellessm", "info@harvelles.com", "photo booth for Harvelle's?",
     "Candlelit 1931 blues/burlesque club, live acts nightly",
     "Oldest live-music venue on the westside; Toledo Show burlesque Sundays",
     "Ticketed shows 7 nights to 2am",
     "Burlesque and blues since 1931 and no booth for the after-show photo — black-and-white strips belong in that room. I'm starting a photo booth route on the westside: vintage-style machine, no cost to you, I install and maintain it, Harvelle's takes a cut of every strip. Who makes that call there?\n\n— Chance"),
    ("Blind Barber", "Culver City · Washington Blvd", T1, "blindbarber_la", None, None,
     "Barbershop-front speakeasy, 1970s styling, DJ + dancefloor",
     "Invite-only 'Secret Show' comedy monthly (Chappelle/Ali Wong drop-ins); grilled cheese menu",
     "Crowded after 9:30pm",
     "A barbershop front, grilled cheese in the back, a secret comedy night — the whole place is already an analog experience. I'm starting a photo booth route on the westside: vintage-style booth, free to the venue, I keep it running, you take a share of every strip. Who makes that call for the Culver room?"),
    ("The Cinema Bar", "Culver City · Sepulveda", T1, "thecinemabar_", None, None,
     "'World's smallest honky-tonk' (1947), family-owned 30 years",
     "Free live music 7 nights, no cover; space genuinely tight",
     "Packed on band nights",
     "World's smallest honky-tonk might be the one westside room where I can't promise the booth fits — but free live music seven nights a week deserves photo strips. I'm starting a booth route: zero cost to the bar, service included, the house takes a cut per vend. Is there honestly nine square feet to spare in there?"),
    ("No Smoking Bar", "Culver City Arts District", T1, "nosmokingbar", None, None,
     "Retro cabin-paneled dive-meets-cocktail bar (ex-Mandrake space)",
     "Opened 2024 in the 18-year Mandrake arts space; frozen ube colada; weekend DJs",
     "'Overcrowded on busy nights', 2am Fri/Sat",
     "Taking over the Mandrake space and keeping the arts crowd — a coin-op photo booth would sit against those cabin panels like it was always there. I'm starting a small route on the westside: booth is free to the venue, I handle all upkeep, the bar takes a cut of each strip. Your call or the owners'?"),
    ("Cozy Inn", "Culver City · Washington Pl", T1, "_cozyinn", None, None,
     "No-frills family dive, 6am-2am, heavy pours, devoted regulars",
     "Vintage shuffleboard mid-bar; own free parking lot",
     "unknown",
     "A shuffleboard table in the middle of the room and your own parking lot — Cozy Inn is the kind of bar photo booths were invented for. I'm starting a small route: the booth costs you nothing, I maintain it, the house gets a cut of every strip. Would the room take a phone-booth footprint somewhere?"),
    ("Chez Jay", "Santa Monica · Ocean Ave", T1, "chezjay1959", "peanuts@chezjays.com", "photo booth for Chez Jay?",
     "Nautical 1959 celebrity dive, peanut shells on the floor",
     "A bar peanut flew to the moon on Apollo 14; 'The Backyard' patio bar",
     "Small room fills nightly",
     "A bar peanut that went to the moon sets a high standard for souvenirs — a photo strip from Chez Jay is the earthbound version. I'm starting a vintage-style booth route on the westside: free to the venue, I handle service, the house shares in every vend. Is the front room or the Backyard even booth-sized?\n\n— Chance"),
    ("The Waterfront Venice", "Venice · boardwalk", T2, "thewaterfrontvenice", None, None,
     "European-style beer garden on the boardwalk, ocean-view patio",
     "Trivia Thursdays; weekend DJ day-parties; ~28-30k boardwalk passersby daily",
     "Boardwalk volume + weekend DJ parties",
     "Trivia Thursdays, weekend DJs, and thirty thousand people walking past on the boardwalk — a photo booth there would never sit idle. I'm starting a small route on the westside: vintage-style booth at no cost to the venue, service included, the house takes a cut of every strip. Who's the right person to run it by?"),
    ("The Venice West", "Venice · Lincoln Blvd", T2, "thevenicewest", "events@venicemusicgroup.com", "photo booth for the Venice West?",
     "Beat-era-inspired live music venue, ticketed shows most nights",
     "Books national acts; Beatles/Dead brunches; line-dancing nights; calendar into 2027",
     "Ticketed shows most nights",
     "Between national acts and line-dancing nights you've got crowds who want proof they were there. I'm starting a photo booth route on the westside — vintage-style machine, free to the venue, I maintain it, you take a share per strip. It's lobby-corner sized. Is that a venue decision or does Venice Music Group make it?\n\n— Chance"),
    ("The Lincoln", "Venice · Lincoln Blvd", T2, "thelincolnvenice", "info@thelincolnvenice.com", "photo booth for The Lincoln?",
     "Dark mid-century cocktail den for Venice locals, opens 7pm",
     "Ford Model T Roadster built into the decor; pours to 2am nightly",
     "unknown",
     "A Model T in the decor and doors that open at 7pm — The Lincoln is a pure night bar, which is exactly when booths earn. I'm starting a small route on the westside: vintage-style photo booth, zero cost to you, I service it, the house takes a cut of each vend. Is there a corner that could take one?\n\n— Chance"),
    ("Baja Cantina", "Marina del Rey · Washington", T2, "bajacantinamdr", None, None,
     "Margarita-and-tequila institution since Sept 1975, fire-pit patio",
     "$15 margarita-flight Thursdays; live local music every weekend",
     "Busy weekends, 1100+ Yelp reviews",
     "Fifty years of margaritas and live music every weekend — Baja strips would be on fridges all over the Marina. I'm starting a photo booth route on the westside: vintage-style booth, free to the venue, I handle everything, the house shares each vend. Who makes that call there?"),
    ("Mo's Place", "Playa del Rey · Culver Blvd", T2, "mosplace_pdr", None, None,
     "PdR's classic sports bar 25+ years, 12+ screens",
     "New management added trivia, patio DJs, live music; Best Sports Bar on the Westside",
     "Game days pack 12+ screens",
     "New management adding trivia, patio DJs, and live music — sounds like the exact moment to add a photo booth too. I'm starting a small route: vintage-style, free to the bar, I service everything, the house takes a cut per strip. Is that your call or the owners'?"),
    ("Joxer Daly's", "Culver City · Washington Blvd", T2, "joxer_d", None, None,
     "Irish pub and sports dive, soccer mornings, pool at night",
     "Thursday karaoke anchor; westside spot for early Premier League broadcasts",
     "Karaoke Thursdays popular, soccer mornings",
     "Thursday karaoke and Premier League mornings — two crowds, both wanting very different photos. I'm starting a small photo booth route on the westside: the booth is free to the pub, I maintain it, the house shares every vend. Would Joxer's have a corner for one?"),
    ("Scarlet Lady Saloon", "Culver City · Sepulveda", T2, "scarlet_lady_saloon", None, None,
     "Strong-pour karaoke dive since 1999, open 8am-2am",
     "Karaoke 5 nights/wk from 9pm; Saints fan bar with full NFL package",
     "unknown",
     "Karaoke five nights a week and a Saints bar on Sundays — that room generates more photo-worthy moments than most clubs. I'm starting a booth route on the westside: vintage-style, costs you nothing, I keep it running, you take a cut of each strip. Who decides that kind of thing there?"),
    ("The Daily Pint", "Santa Monica · Pico", T2, "thedailypintsm", "thedailypint@yahoo.com", "photo booth for the Pint?",
     "British-leaning whiskey-and-beer dive, BYO food",
     "3 cask ales on hand pumps (Imbibe best-cask list); 500-bottle whiskey wall; shuffleboard",
     "unknown",
     "Cask ale on hand pumps and a five-hundred-bottle whiskey wall — the Pint is already an analog bar, and a film-look photo booth fits that. I'm starting a small route on the westside: free to the venue, I service it, the house takes a share per vend. Is there floor space anywhere near the shuffleboard?\n\n— Chance"),
    ("Sonny McLean's", "Santa Monica · Wilshire", T2, "sonnymcleans", None, None,
     "Boston-in-exile Irish sports pub, 29 TVs + beer garden",
     "#1 Patriots bar on the West Coast; 9am weekend openings for East Coast kickoffs",
     "Boston game days pack the room",
     "The #1 Pats bar on the West Coast — every Boston win in that room ends in group photos that never get printed. I'm starting a photo booth route on the westside: vintage-style booth, free to the bar, all service on me, the house takes a cut per strip. Your call or the owner's?"),
    ("Santa Monica Brew Works", "Santa Monica · Colorado Ave", T2, "santamonicabrewworks", "info@santamonicabrewworks.com", "photo booth for the taproom?",
     "SM's only production brewery; industrial taproom + beer garden",
     "11.5-ft outdoor jumbotron installed for World Cup 2026; Tuesday trivia; Emmy Squared pizza",
     "World Cup viewing hub positioning",
     "An 11.5-foot jumbotron ahead of the World Cup — you're clearly investing in reasons for people to stay. A photo booth is the cheapest one there is: free to the taproom, I install and maintain it, you share in each vend. Who's the right person for that conversation?\n\n— Chance"),
    ("Alibi Room", "Del Rey · W Washington", T2, "alibiroomla", "info@alibiroomla.com", "photo booth for Alibi Room?",
     "Low-lit neighborhood lounge, 30+ beers, westside date spot",
     "Roy Choi's Kogi test kitchen — Kogi tacos from the bar kitchen; glass-door patio",
     "Steady dinner crowds, 1600+ Yelp",
     "Kogi tacos out of the kitchen and a patio behind glass doors — date-night central. I'm starting a vintage-style photo booth route on the westside: no cost to the venue, I run the machine, the house takes a cut per strip. Is that a you-decision or an ownership one?\n\n— Chance"),
    ("Accomplice Bar", "Mar Vista · Grand View", T2, "accomplice_bar", "info@littlefattyla.com", "photo booth for Accomplice?",
     "Acclaimed cocktail bar attached to Little Fatty, date-spot energy",
     "Top-10 US cocktail bar, 2024 Spirited Awards; Hainan-chicken-mezcal signature drink",
     "unknown",
     "A Spirited Awards top-ten bar with a chicken-fat-mezcal signature — people already treat a visit as an event; strips make it a souvenir. I'm starting a small booth route: free to you, I service it, the house shares each vend. Who makes that call for Accomplice?\n\n— Chance"),
    ("The Wellesbourne", "West LA · Pico", T2, "thewellesbourne", None, None,
     "Candlelit English manor-house lounge, book-lined walls",
     "Live jazz select nights in the library room",
     "unknown",
     "A book-lined manor room with live jazz — a vintage black-and-white photo booth is about the only machine that wouldn't break the spell. I'm starting a small route on the westside: free to the venue, I handle upkeep, the house takes a cut per strip. Who decides on additions like that?"),
    ("Dots Space LA", "Sawtelle Japantown", T2, "dotsspace_la", "info@dotsspacela.com", "photo booth for Dots?",
     "Neon karaoke lounge, public stage + bar, open to 4am nightly",
     "4 themed private karaoke rooms bookable to 3am",
     "unknown",
     "Four themed karaoke rooms and 4am closes — everyone leaves mid-adrenaline and empty-handed. A coin-op photo booth by the stage fixes that: free to you, I install and maintain it, Dots takes a share of every strip. Is that your call?\n\n— Chance"),
    ("Purple Orchid", "El Segundo · Richmond St", T2, "purpleorchidtikilounge", None, None,
     "Kitschy tiki dive since 2001, tropical drinks till 2am",
     "2 pool tables under the tiki decor; live bands weekend nights",
     "'Really busy and crowded' Fridays",
     "Packed Fridays under the tiki decor since 2001 — a vintage photo booth in that room would never be empty. I'm starting a small route: costs the bar nothing, I service it, the house takes a cut per strip. Would there be a corner for one?"),
    ("Melody Bar & Grill", "Westchester · Sepulveda", T2, "melodylax", None, None,
     "Independent 1952 roadside bar near LAX; locals + airport crews",
     "Wednesday karaoke; monthly live music, themed DJ parties, comedy",
     "unknown",
     "Wednesday karaoke, comedy nights, and the same corner since 1952 — Melody's the kind of room photo strips were made in. I'm starting a booth route: vintage-style, free to the bar, I keep it running, the house shares each vend. Who makes that call there?"),
    ("Father's Office", "Culver City · Helms", T3, "fathersofficeofficial", "info@fathersoffice.com", "photo booth for the Helms patio crowd?",
     "Landmark Helms Bakery gastropub, 36 taps (Sang Yoon group)",
     "No-substitutions Office Burger; Helms patio with free lot parking",
     "'Packed almost every night'",
     "The Helms room stays packed almost every night — while people wait on burgers, a photo booth pays rent. I'm starting a small route of vintage-style booths on the westside: no cost to the venue, I service everything, the house takes a cut per strip. Does that route through the group or the GM?\n\n— Chance"),
    ("Firestone Walker Propagator", "Marina del Rey · Washington", T3, "firestonewalker_propagator", None, None,
     "Pilot brewhouse + gastropub taproom (corporate parent)",
     "On-site R&D brewhouse makes Venice-only beers; Tuesday trivia $22 pizza+pint",
     "1100+ Yelp, game-day crowds",
     "Venice-only beers out of the R&D brewhouse — the Propagator is the one Firestone room quirky enough for a vintage photo booth. I'm starting a small route: free to the venue, I handle service, the house shares each vend. Is that a local-GM decision or corporate?"),
    ("LA Ale Works Culver City", "Culver City · Ivy Station", T3, "laaleworks", "info@laaleworks.com", "photo booth for the Ivy Station taproom?",
     "Modern 21+ brewery taproom at Ivy Station, 25 taps",
     "Lucky Guess Trivia Tuesdays with organized meetup groups; at the Metro E Line escalators",
     "Time Out 'local hit'",
     "Trivia Tuesdays with organized teams and the E Line at your door — group crowds are what feed photo booths. I'm starting a small route on the westside: booth is free to the taproom, serviced by me, with a revenue share on every strip. GM call or ownership?\n\n— Chance"),
    ("Barney's Beanery Westwood", "Westwood Village", T3, "barneysbeaneryww", "info@barneysbeanery.com", "photo booth for the Westwood room?",
     "Roadhouse-style UCLA hangout, billiards + arcade (small chain)",
     "Trivia Tuesdays 8:30pm; 21+ karaoke Thursdays 10pm",
     "Daily Bruin staple, UCLA game days",
     "Billiards, arcade games, and Thursday karaoke two blocks from campus — students print nothing, and this is the one thing they'd print. I'm starting a vintage-style photo booth route: free to the venue, I maintain it, the house takes a cut per vend. Who decides for the Westwood location?\n\n— Chance"),
    ("Rocco's Tavern Westwood", "Westwood Village", T3, "roccoswestwood", None, None,
     "THE UCLA bar at Gayley & Weyburn (small chain)",
     "Live-band karaoke nights alongside game-day broadcasts",
     "Central student nightlife spot",
     "Live-band karaoke plus every UCLA game — that's two photo-hungry crowds a week. I'm starting a photo booth route on the westside: vintage-style booth, free to the bar, service included, the house shares each strip. Is that decided in-house or at the group level?"),
    ("The Chestnut Club", "Santa Monica · 14th St", T3, "thechestnutclub", "marketing@happytoserveyou.com", "photo booth for Chestnut?",
     "Moody spirits-driven den, deliberately zero TVs (HTSY group)",
     "400+ bottle back bar; bartender 'preference interview' ritual",
     "unknown",
     "A room with deliberately zero TVs — a vintage photo booth is the one machine that agrees with that philosophy. I'm starting a small route on the westside: free to the venue, I handle everything, the house takes a cut per strip. Who would make that call for Chestnut?\n\n— Chance"),
    ("Library Alehouse", "Santa Monica · Main St", T3, "libraryalehouse", "info@libraryalehouse.com", "photo booth for the Alehouse?",
     "Wood-paneled craft-beer gastropub since 1995",
     "One of LA's first craft-beer bars; restored 2022 by two young co-owners; 29 Cicerone-curated taps",
     "unknown",
     "One of LA's first craft-beer bars, freshly restored — a film-look booth fits the wood paneling better than any TV would. I'm starting a small route on the westside: free to the venue, I service it, the house shares each vend. Is that an owners' decision or a GM one?\n\n— Chance"),
    ("The Brixton", "Santa Monica · Pico", T3, "thebrixtonsm", "events@thebrixtonsm.com", "photo booth for the Brixton?",
     "Casual Pico gastropub-sports hybrid, families early, games late",
     "Latin Night parties; Saturday bottomless brunch from 9:30am",
     "unknown",
     "Latin Nights and bottomless Saturdays — groups who already dress for photos. I'm starting a vintage-style photo booth route on the westside: free to the venue, I keep it running, the house takes a cut per strip. Who's the right person there?\n\n— Chance"),
    ("The Mulberry", "Sawtelle Japantown", T3, "themulberryla", None, None,
     "New (Jan 2026) Michelin-Guide Korean-American bistro + late bar",
     "Bar pours to 2am Thu-Sat — nearly the only late option on Sawtelle",
     "Michelin/Resy buzz, no line reports yet",
     "The only bar pouring past midnight on Sawtelle — last-call crowds leave with nothing to show for it. I'm starting a small photo booth route: vintage-style, no cost to the venue, service included, the house shares each vend. Too new to say yes, or exactly the right time?"),
    ("El Segundo Brewing", "El Segundo · Main St", T3, "esbcbrews", "info@elsegundobrewing.com", "photo booth for the taproom?",
     "Hop-forward production brewery taproom on Main St",
     "Brews Stone Cold Steve Austin's Broken Skull IPA on site; closes 9-10pm",
     "unknown",
     "Home of the Broken Skull IPA — the pilgrimage crowd wants proof they made it to the source. I'm starting a small photo booth route: free to you, I maintain it, the house takes a cut per strip. Is there floor space for a phone-booth footprint?\n\n— Chance"),
    ("Brewport Tap House", "El Segundo · Main St", T3, "brewporttaphouse", None, None,
     "Self-pour craft beer hall, front/back patios + beer garden",
     "60 wristband self-pour taps; 'Trivia with BUDDS' Tuesdays 7pm",
     "unknown",
     "Sixty self-pour taps and trivia with BUDDS — you've built the interactive taproom; a coin-op photo booth is the missing station. I'm starting a small route: free to the venue, I service it, the house shares each vend. GM call or ownership?"),
]


def main() -> None:
    with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
        cur.execute("select id from campaigns where slug = 'photobooth-route'")
        row = cur.fetchone()
        if not row:
            raise SystemExit("photobooth-route campaign missing — run scripts.sync_campaigns first")
        campaign_id = row[0]
        cur.execute("select id from profiles where is_admin limit 1")
        admin = cur.fetchone()
        admin_id = admin[0] if admin else None

        leads_new = drafts_new = 0
        for name, area, tier, ig, email, subject, vibe, hook, busy, msg in VENUES:
            ig_url = f"https://instagram.com/{ig}"
            cur.execute(
                """
                insert into leads (linkedin_url, name, headline, company, role, location,
                                   campaign_id, user_id, email, source, status, updated_at)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,'manual:photobooth-route','drafted', now())
                on conflict (linkedin_url) do update set updated_at = now()
                returning id, (xmax = 0) as inserted
                """,
                (ig_url, name, vibe, area, tier, "Westside LA",
                 campaign_id, admin_id, email),
            )
            lead_id, inserted = cur.fetchone()
            leads_new += 1 if inserted else 0

            channel = "manual_email" if email and subject else "manual_ig"
            hook_obj = {
                "type": "venue-context",
                "reference": hook,
                "why_it_matters": busy,
                "signal_strength": SIG[tier],
            }
            if subject:
                hook_obj["subject"] = subject
            cur.execute(
                """
                insert into drafts (lead_id, channel, step_index, hook, body, status, variant)
                values (%s, %s, 0, %s, %s, 'draft', 'manual')
                on conflict (lead_id, channel, step_index, variant) do nothing
                """,
                (lead_id, channel, Jsonb(hook_obj), msg),
            )
            drafts_new += cur.rowcount
        conn.commit()
        print(f"venues processed: {len(VENUES)}  leads inserted: {leads_new}  drafts inserted: {drafts_new}")

        cur.execute(
            """
            select d.channel, count(*) from drafts d
            join leads l on l.id = d.lead_id
            where l.campaign_id = %s and d.status = 'draft'
            group by 1 order by 1
            """,
            (campaign_id,),
        )
        for ch, n in cur.fetchall():
            print(f"  pending {ch}: {n}")


if __name__ == "__main__":
    main()
