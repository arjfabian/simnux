"""Async stream abstractions for command I/O (pipes, redirection)."""

from abc import ABC
from abc import abstractmethod
import asyncio
import logging

from simnux.filesystem.vfs import SNXFileSystem


logger = logging.getLogger("simnux.commands.streams")


class AsyncStreamReader(ABC):
    """Async reader protocol for command stdin."""

    @abstractmethod
    async def readline(self) -> str | None:
        """Read one line. Returns None at EOF."""

    def __aiter__(self):
        return self

    @abstractmethod
    async def __anext__(self) -> str:
        """Iterate lines until EOF (raises StopAsyncIteration)."""


class AsyncStreamWriter(ABC):
    """Async writer protocol for command stdout/stderr."""

    @abstractmethod
    async def write(self, data: str) -> None:
        """Write a single line (backpressure via underlying queue)."""

    async def writelines(self, lines: list[str]) -> None:
        for line in lines:
            await self.write(line)

    @abstractmethod
    def close(self) -> None:
        """Signal EOF; subsequent writes raise ValueError."""


class QueueStreamReader(AsyncStreamReader):
    """AsyncStreamReader backed by an asyncio.Queue.

    Uses None as the EOF sentinel for natural backpressure.
    """

    def __init__(self, queue: asyncio.Queue) -> None:
        self._queue = queue
        self._eof = False

    def has_pending(self) -> bool:
        """Return True if the queue has a non-None item available (non-blocking).

        Drains and re-enqueues in original order so queue order is preserved.
        """
        if self._queue.empty():
            return False
        items: list = []
        while not self._queue.empty():
            try:
                items.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        for item in items:
            self._queue.put_nowait(item)
        return any(item is not None for item in items)

    async def readline(self) -> str | None:
        if self._eof:
            return None
        data = await self._queue.get()
        if data is None:
            self._eof = True
            return None
        return data

    async def __anext__(self) -> str:
        result = await self.readline()
        if result is None:
            raise StopAsyncIteration
        return result


class QueueStreamWriter(AsyncStreamWriter):
    """AsyncStreamWriter backed by an asyncio.Queue.

    close() enqueues a None EOF sentinel that QueueStreamReader
    recognizes as end-of-stream.
    """

    def __init__(self, queue: asyncio.Queue) -> None:
        self._queue = queue
        self._closed = False

    async def write(self, data: str) -> None:
        if self._closed:
            raise ValueError("Stream is closed")
        await self._queue.put(data)

    def close(self) -> None:
        self._closed = True
        self._queue.put_nowait(None)


class FileStreamWriter(AsyncStreamWriter):
    """AsyncStreamWriter that buffers writes and flushes to a VFS file.

    On ``close()``, all buffered data is joined and written to the VFS at
    ``path``. If the file does not yet exist it is created (``touch``).
    ``append=False`` → ``write()`` (truncate); ``append=True`` → ``append()``.

    After ``close()``, ``last_error`` contains the error message from the
    VFS if the write/append was rejected (e.g. ``DISK_QUOTA_EXCEEDED``),
    or ``None`` on success.
    """

    def __init__(
        self,
        filesystem: SNXFileSystem,
        path: str,
        append: bool = False,
    ) -> None:
        self._filesystem = filesystem
        self._path = path
        self._append = append
        self._lines: list[str] = []
        self._closed = False
        self.last_error: str | None = None

    async def write(self, data: str) -> None:
        if self._closed:
            raise ValueError("Stream is closed")
        self._lines.append(data)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        content = "".join(self._lines)
        try:
            if not self._filesystem.exists(self._path):
                self._filesystem.touch(self._path)
            if self._append:
                result = self._filesystem.append(self._path, content)
            else:
                result = self._filesystem.write(self._path, content)
            if result.message:
                self.last_error = str(result.message)
        except Exception:
            logger.exception("FileStreamWriter: failed to flush to %s", self._path)
            self.last_error = "write failed"
