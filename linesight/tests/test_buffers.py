import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trackmania_rl.buffer_utilities import make_buffers, resize_buffers


def contents(buffer):
    return sorted(item[0] if isinstance(item, list) else item for item in buffer._storage._storage)


class ResizeTests(unittest.TestCase):
    def filled(self, size, count):
        buffer, buffer_test = make_buffers(size)
        for i in range(count):
            buffer.extend([i])
        return buffer, buffer_test

    def test_shrinking_keeps_the_newest_memories(self):
        buffer, buffer_test = self.filled(10, 15)
        smaller, _ = resize_buffers(buffer, buffer_test, 4)
        self.assertEqual(contents(smaller), [11, 12, 13, 14])

    def test_shrinking_a_part_full_buffer(self):
        buffer, buffer_test = self.filled(10, 6)
        smaller, _ = resize_buffers(buffer, buffer_test, 4)
        self.assertEqual(contents(smaller), [2, 3, 4, 5])

    def test_growing_keeps_everything(self):
        buffer, buffer_test = self.filled(10, 15)
        bigger, _ = resize_buffers(buffer, buffer_test, 20)
        self.assertEqual(contents(bigger), list(range(5, 15)))

    def test_empty_buffers(self):
        buffer, buffer_test = make_buffers(10)
        smaller, smaller_test = resize_buffers(buffer, buffer_test, 4)
        self.assertEqual(len(smaller), 0)
        self.assertEqual(len(smaller_test), 0)


if __name__ == "__main__":
    unittest.main()
