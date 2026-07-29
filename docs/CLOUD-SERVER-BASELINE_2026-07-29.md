# Cloud-Server-Baseline

Abrufstand: 2026-07-29. Preise sind Momentaufnahmen, keine dauerhaft gültigen
Konstanten. Vor einer Beschaffung müssen Region, Steuern, Währung, Transfer,
Backups, IPv4, Storage und Anbieterbedingungen live neu geprüft werden.

## Vergleichbare Einstiegspunkte

| Anbieter | Beobachteter Einstieg | Wichtige Bedingungen |
|---|---|---|
| DigitalOcean Basic | 512 MiB, 1 vCPU, 10 GiB SSD, 500 GiB Transfer: 4 USD/Monat; 1 GiB: 6 USD; 2 GiB: 12 USD | seit 2026-01-01 sekundengenaue Abrechnung mit Mindestbetrag; monatlicher Cap; Backups und Snapshots zusätzlich |
| AWS Lightsail Linux, öffentliche IPv4 | 0,5 GiB/2 vCPU/20 GB/1 TB: 5 USD; 1 GiB: 7 USD; 2 GiB: 12 USD; 4 GiB: 24 USD pro Monat | IPv6-only ab 3,50 USD; Transferkontingente und Preise können regionsabhängig sein |
| Google Compute Engine | kein neutraler fixer Einstiegspreis übernommen | maschinen-, regions- und nutzungsabhängig; offizielle Preisseite/Calculator bei jeder Analyse abrufen |
| Hetzner Cloud | kein Betrag als dauerhaft aktuell übernommen | Hetzner veröffentlichte eine Preis-/Produktanpassung mit Wirkung 2026-06-15; live Calculator/Preisseite neu abrufen |

Offizielle Preisquellen:

- <https://www.digitalocean.com/pricing/droplets>
- <https://aws.amazon.com/lightsail/pricing/>
- <https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-bundles.html>
- <https://cloud.google.com/products/compute/pricing>
- <https://www.hetzner.com/cloud/>
- <https://www.hetzner.com/pressroom/standardization-and-price-adjustment-of-our-server-products/>

## Sicherheitsbaseline

Ein „Privatserver“ ist nur dann zweckerfüllend, wenn ungewollter öffentlicher
Zugriff aus externer Sicht blockiert ist. Providerdeklaration oder lokale
Erreichbarkeitsprüfung allein genügt nicht.

Hetzner dokumentiert für Cloud Firewalls: Ohne Inbound-Regeln wird eingehender
Traffic blockiert, ausgehender Traffic bleibt erlaubt; die Firewall selbst ist
kostenfrei:
<https://docs.hetzner.com/cloud/firewalls/overview/>.

AWS Lightsail führt unabhängige IPv4- und IPv6-Firewalls. Regeln sind
erlaubend; manche Images öffnen standardmäßig SSH, HTTP oder HTTPS für alle
IP-Adressen. Beide Protokollfamilien müssen daher getrennt geprüft werden:
<https://docs.aws.amazon.com/lightsail/latest/userguide/understanding-firewall-and-port-mappings-in-amazon-lightsail.html>.

Für teiloffene APIs gehören Authentifizierung, Anti-Brute-Force/Rate-Limits
und ein aktuelles Oberflächeninventar zur Zweckprüfung:
<https://owasp.org/API-Security/editions/2023/en/0xa2-broken-authentication/>
und <https://owasp.org/www-project-api-security/>.

## Entscheidungsregel

Ein Cloudserver lohnt sich nicht allein, weil sein Listenpreis niedriger als
lokale Hardware ist. Explorer weist mindestens separat aus:

1. monetäre Monatskosten inklusive Nebenpositionen;
2. lokale effektive Monatskosten einschließlich Amortisierung, Strom und
   Administration;
3. Zweckdeckung und benötigte Ortsunabhängigkeit;
4. öffentliche Angriffsfläche und Schutzdeckung;
5. Verfügbarkeit, Latenz, Datenort, Backup-/Restoreweg und Lock-in.
