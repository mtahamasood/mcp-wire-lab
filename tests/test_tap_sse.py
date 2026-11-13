"""The tap's SSE parser, called directly (phase 8 C22, review finding P8-R7-1).

No subprocess and no network. The scaling tests feed one large event in small pieces and
compare the time for 4x the input with the time for 1x: a linear parser takes about 4x, the old
parser (which rescanned its whole buffer for each piece) took about 16x. The margins are wide
(best of three runs, a floor under which the time is noise) so a loaded CI runner does not
flake.
"""

from __future__ import annotations

import time
import unittest

from tap.http import SseEvent, SseParser

PIECE = 16 * 1024
SMALL = 1024 * 1024
BIG = 4 * SMALL
NOISE_FLOOR = 1.0  # seconds; the quadratic parser needs many times this at BIG


def feed_all(data: bytes, piece: int) -> tuple[list[SseEvent], SseParser]:
    parser = SseParser()
    events: list[SseEvent] = []
    for i in range(0, len(data), piece):
        events += parser.feed(data[i : i + piece])
    return events, parser


def best_time(data: bytes, piece: int) -> float:
    best = float("inf")
    for _ in range(3):
        start = time.perf_counter()
        feed_all(data, piece)
        best = min(best, time.perf_counter() - start)
    return best


def one_event(size: int) -> bytes:
    return b'data: {"jsonrpc":"2.0","id":1,"result":{"blob":"' + b"x" * size + b'"}}\n\n'


class SseParserScalingTest(unittest.TestCase):
    def assert_linear(self, small: bytes, big: bytes, piece: int) -> None:
        t_small = best_time(small, piece)
        t_big = best_time(big, piece)
        limit = max(8 * t_small, NOISE_FLOOR)
        self.assertLess(
            t_big, limit,
            f"4x the input took {t_big:.3f}s against {t_small:.3f}s for 1x (limit {limit:.3f}s)",
        )

    def test_large_event_in_small_pieces_scales_linearly(self) -> None:
        self.assert_linear(one_event(SMALL), one_event(BIG), PIECE)

    def test_large_event_is_parsed_whole(self) -> None:
        events, _ = feed_all(one_event(BIG), PIECE)
        (event,) = events
        self.assertEqual(len(event.data), len(one_event(BIG)) - len(b"data: ") - 2)
        self.assertTrue(event.data.startswith(b'{"jsonrpc"'))

    def test_many_lines_in_one_chunk_scale_linearly(self) -> None:
        def lines(count: int) -> bytes:
            return b"".join(b"data: line %d\n" % i for i in range(count)) + b"\n"

        small, big = lines(20_000), lines(80_000)
        self.assert_linear(small, big, len(big))

    def test_many_small_events_scale_linearly(self) -> None:
        def events(count: int) -> bytes:
            return b"".join(b"id: %d\ndata: {}\n\n" % i for i in range(count)) + b""

        small, big = events(20_000), events(80_000)
        self.assert_linear(small, big, PIECE)


class SseParserFramingTest(unittest.TestCase):
    def test_line_ends_lf_crlf_cr_all_frame_events(self) -> None:
        for end in (b"\n", b"\r\n", b"\r"):
            with self.subTest(end=end):
                events, _ = feed_all(b"id: 7" + end + b"data: a" + end + end + b"x", 1024)
                (event,) = events
                self.assertEqual((event.data, event.id), (b"a", "7"))

    def test_mixed_line_ends_in_one_event(self) -> None:
        events, _ = feed_all(b"data: a\r\ndata: b\rdata: c\n\r\n", 1024)
        (event,) = events
        self.assertEqual(event.data, b"a\nb\nc")

    def test_multi_line_data_joined_with_newline(self) -> None:
        events, _ = feed_all(b"event: message\ndata: one\ndata: two\ndata:\ndata: four\n\n", 1024)
        (event,) = events
        self.assertEqual(event.data, b"one\ntwo\n\nfour")
        self.assertEqual(event.event, "message")

    def test_one_leading_space_is_stripped_from_the_value(self) -> None:
        events, _ = feed_all(b"data:  two spaces\ndata:none\n\n", 1024)
        (event,) = events
        self.assertEqual(event.data, b" two spaces\nnone")

    def test_event_split_at_every_byte_boundary(self) -> None:
        stream = b": hi\r\nid: 3\r\nretry: 250\r\ndata: x\r\ndata: y\r\n\r\ndata: z\n\n"
        whole, whole_parser = feed_all(stream, len(stream))
        for piece in (1, 2, 3, 5, 7):
            with self.subTest(piece=piece):
                events, parser = feed_all(stream, piece)
                self.assertEqual(events, whole)
                self.assertEqual(parser.comments, whole_parser.comments)
        self.assertEqual([e.data for e in whole], [b"x\ny", b"z"])
        self.assertEqual((whole[0].id, whole[0].retry), ("3", 250))
        self.assertEqual(whole_parser.comments, 1)

    def test_cr_at_chunk_end_waits_for_a_possible_lf(self) -> None:
        parser = SseParser()
        self.assertEqual(parser.feed(b"data: a\r"), [])
        self.assertEqual(parser.feed(b"\n"), [])  # the CRLF ends the line; the event is open
        self.assertEqual(parser.feed(b"\r"), [])  # a CR ends the chunk: still may be CRLF
        (event,) = parser.feed(b"x")  # it was a lone CR, the blank line
        self.assertEqual(event.data, b"a")
        parser = SseParser()
        self.assertEqual(parser.feed(b"data: b\r"), [])
        (event,) = parser.feed(b"\rdata: c")  # CR then CR: two lines, the second blank
        self.assertEqual(event.data, b"b")

    def test_partial_line_across_chunks_is_kept(self) -> None:
        parser = SseParser()
        self.assertEqual(parser.feed(b"da"), [])
        self.assertEqual(parser.feed(b"ta: hel"), [])
        self.assertEqual(parser.feed(b"lo\n"), [])
        (event,) = parser.feed(b"\n")
        self.assertEqual(event.data, b"hello")

    def test_unknown_and_bad_retry_fields_are_ignored(self) -> None:
        events, _ = feed_all(b"unknown: x\nretry: abc\n\ndata: ok\n\n", 1024)
        (event,) = events
        self.assertEqual((event.data, event.retry), (b"ok", None))

    def test_finish_returns_the_cut_off_event_as_partial(self) -> None:
        parser = SseParser()
        self.assertEqual(parser.feed(b"data: a\ndata: b"), [])
        event = parser.finish()
        assert event is not None
        self.assertEqual((event.data, event.partial), (b"a\nb", True))
        self.assertIsNone(parser.finish())

    def test_finish_drops_a_trailing_cr_and_an_untouched_tail(self) -> None:
        parser = SseParser()
        parser.feed(b"data: a\r")
        event = parser.finish()
        assert event is not None
        self.assertEqual(event.data, b"a")
        parser = SseParser()
        parser.feed(b"data: a\n\n")
        self.assertIsNone(parser.finish())

    def test_comments_are_counted_and_not_events(self) -> None:
        events, parser = feed_all(b": a\n:b\r\n: c\r\n", 1024)
        self.assertEqual(events, [])
        self.assertEqual(parser.comments, 3)


if __name__ == "__main__":
    unittest.main()
