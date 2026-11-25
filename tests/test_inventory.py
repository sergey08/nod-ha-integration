import runpy
import unittest

inventory = runpy.run_path("custom_components/nod/inventory.py")["inventory"]

class InventoryTest(unittest.TestCase):
    def test_components_are_scoped_to_the_selected_server(self):
        server = {"slug": "one_nod_native_preflight", "version": "1"}
        foreign = {"slug": "two_nod_browser_preflight", "version": "2"}
        self.assertEqual(inventory([server, foreign], "one"), {"Server": server, "Browser": None, "Workspace": None})
