import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import paths


class WinePathTests(unittest.TestCase):
    def test_unix_paths_go_through_z(self):
        self.assertEqual(paths.unix_to_wine("/home/joe/Games/TrackMania Nations Forever"), "Z:\\home\\joe\\Games\\TrackMania Nations Forever")
        self.assertEqual(paths.wine_to_unix("Z:\\home\\joe\\Games\\TrackMania Nations Forever"), "/home/joe/Games/TrackMania Nations Forever")

    def test_drive_c_stays_in_the_prefix(self):
        inside = os.path.join(paths.WINEPREFIX, "drive_c", "Games", "TMNF")
        wine = paths.unix_to_wine(inside)
        self.assertTrue(wine.startswith("C:"))
        self.assertEqual(os.path.normpath(paths.wine_to_unix(wine)), os.path.normpath(inside))

    def test_helper_ports_fit_in_the_block(self):
        offsets = (paths.FOLLOWER_PORT_OFFSET, paths.BRUTEFORCE_PORT_OFFSET, paths.BENCHMARK_PORT_OFFSET)
        self.assertTrue(all(paths.HELPER_PORT_OFFSET <= o < paths.PORT_BLOCK for o in offsets))


if __name__ == "__main__":
    unittest.main()
