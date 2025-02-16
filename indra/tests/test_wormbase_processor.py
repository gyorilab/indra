from unittest import TestCase
import os
from indra.sources.wormbase import *


this_dir = os.path.dirname(__file__)
test_file_gen = os.path.join(this_dir, 'wormbase_tests_data/INTERACTION-GEN_WB_test.tsv')
test_file_mol = os.path.join(this_dir, 'wormbase_tests_data/INTERACTION-MOL_WB_3_test.tsv')
test_file_map = os.path.join(this_dir, 'wormbase_tests_data/wormbase_entrez_mappings.tsv')



class TestWormBaseProcessor(TestCase):

    def test_statements_creation(self):
        """Test attributes and properties of the `statements` list in WormBaseProcessor."""

        try:
            # Create a WormBaseProcessor instance with test files
            processor = process_from_files(test_file_gen, test_file_mol, test_file_map)

            # Ensure `statements` has been populated
            self.assertGreater(len(processor.statements), 0, "The statements list should not be empty.")

        except Exception as e:
            self.fail(f"Test failed due to an exception: {e}")


if __name__ == "__main__":
    import unittest

    unittest.main()
