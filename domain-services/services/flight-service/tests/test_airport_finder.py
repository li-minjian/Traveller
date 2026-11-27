import unittest

from airport_finder import Airport, AirportFinder

from .helpers import BERLIN, LONDON


def airport(iata: str, lat: float, lon: float) -> Airport:
    return Airport(iata, f"{iata} Airport", "", "DE", lat, lon, "Europe/Berlin", True)


class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.finder = AirportFinder.from_files()

    def codes(self, point, **options):
        return [n.airport.iata for n in self.finder.nearest(point["latitude"], point["longitude"], **options).airports]

    def test_berlin_and_london(self):
        self.assertEqual(self.codes(BERLIN), ["BER"])
        self.assertEqual(self.codes(LONDON), ["LCY", "LHR"])  # nearest first; LGW is 40 km away
        self.assertEqual(self.codes(LONDON, radius_km=50), ["LCY", "LHR", "LGW"])  # at most 3

    def test_closed_and_unusable_airports_are_ignored(self):
        everything = {n.airport.iata for n in self.finder.nearest(52.52, 13.405, radius_km=40, max_airports=50).airports}
        self.assertNotIn("TXL", everything)  # Berlin Tegel, closed
        self.assertNotIn("THF", everything)  # Berlin Tempelhof, closed

    def test_radius_grows_until_an_airport_is_found(self):
        area = self.finder.nearest(40.0, -40.0)  # middle of the Atlantic
        self.assertGreater(area.radius_km, 30)
        self.assertEqual(area.radius_km % 10, 0)  # grows in 10 km steps
        self.assertLessEqual(area.airports[0].distance_km, area.radius_km)
        self.assertGreater(area.airports[0].distance_km, area.radius_km - 10)

    def test_airports_have_time_zones(self):
        [nearby] = self.finder.nearest(**{"latitude": 52.52, "longitude": 13.405}).airports
        self.assertEqual(nearby.airport.time_zone, "Europe/Berlin")
        self.assertLess(nearby.distance_km, 25)


class SearchAreaTests(unittest.TestCase):
    def setUp(self):
        self.finder = AirportFinder([airport("AAA", 0.0, 0.1), airport("BBB", 0.0, 0.5), airport("CCC", 0.0, 3.0)])

    def test_all_airports_in_radius_nearest_first(self):
        area = self.finder.nearest(0.0, 0.0, radius_km=60)
        self.assertEqual([n.airport.iata for n in area.airports], ["AAA", "BBB"])
        self.assertEqual(area.radius_km, 60)

    def test_radius_grows_in_steps_until_the_first_airport(self):
        area = self.finder.nearest(0.0, 2.9, radius_km=5, step_km=2)  # CCC is ~11.1 km away
        self.assertEqual(area.radius_km, 13)
        self.assertEqual([n.airport.iata for n in area.airports], ["CCC"])

    def test_default_start_is_30_km(self):
        self.assertEqual(self.finder.nearest(0.0, 0.0).radius_km, 30)

    def test_max_radius_is_a_safety_limit(self):
        area = self.finder.nearest(60.0, 60.0, radius_km=30, max_radius_km=400)
        self.assertEqual((area.radius_km, area.airports), (400, ()))

    def test_invalid_settings(self):
        with self.assertRaises(ValueError):
            self.finder.nearest(0, 0, radius_km=0)
