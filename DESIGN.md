# Sime Loop interface

The supplied sketches and palette are the visual authority. The interface supports brief outdoor tasks: residents scan a station and see their points; cleaners find a full compartment and record a collection.

Brand red #D71920 signals primary actions. Charcoal #292929 carries headings. White surfaces and #F5F5F5 backgrounds keep data readable. Pale orange #FFF0E6 frames the recycling invitation, and pale yellow #FFF5D6 identifies demonstration tools. Status always includes a text label in addition to colour: green available, red full, orange in use, muted offline.

DM Sans is bundled for offline typography. Reusable components live in `mobile/src/ui.tsx`. The green and terracotta bin illustration connects food and recyclable streams without inventing impact metrics.

Compact screens have five bottom destinations for residents and two for cleaners; expanded screens use a left rail. The point balance and notification button remain visible. Native safe areas and the system Back action are respected. The web build previews the same Expo application.

The iPad web kiosk extends this identity with two large recyclable/food touch targets, authored vector material illustrations, a compact local leaderboard and three labelled capacities. It fits a 1024×768 landscape iPad and reflows vertically on phones. A separate QR/check/mismatch/sorting/completion flow replaces the two choices while a resident uses the station. Category selection reserves the destination; verification controls the internal door. Its surface brief is `docs/KIOSK_DESIGN.md`.

Rewards are explicitly illustrative. A classified image cannot itself credit points. The deposit sheet distinguishes camera verification, physical sensor confirmation, and labelled demo controls. Empty states, disabled rewards, network retry, session expiry, QR permission denial, uncertain classifications, and voucher expiry are part of the flow.
