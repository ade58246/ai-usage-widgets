from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    activation_requested = Signal()

    def __init__(self, name: str = "claude-usage-widget-v1", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.name = name
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._accept_connections)
        self._primary = False
        self._sockets: set[QLocalSocket] = set()

    def acquire(self) -> bool:
        probe = QLocalSocket(self)
        probe.connectToServer(self.name)
        if probe.waitForConnected(250):
            probe.write(b"show\n")
            probe.waitForBytesWritten(250)
            probe.waitForReadyRead(500)
            probe.disconnectFromServer()
            probe.deleteLater()
            return False
        QLocalServer.removeServer(self.name)
        self._primary = self._server.listen(self.name)
        return self._primary

    def close(self) -> None:
        for socket in tuple(self._sockets):
            socket.abort()
        self._sockets.clear()
        if self._server.isListening():
            self._server.close()
        if self._primary:
            QLocalServer.removeServer(self.name)
        self._primary = False

    def _accept_connections(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                continue
            self._sockets.add(socket)
            socket.readyRead.connect(lambda socket=socket: self._read_activation(socket))
            socket.disconnected.connect(lambda socket=socket: self._drop_socket(socket))

    def _read_activation(self, socket: QLocalSocket) -> None:
        if b"show" in bytes(socket.readAll()):
            self.activation_requested.emit()
        socket.write(b"ok\n")
        socket.flush()

    def _drop_socket(self, socket: QLocalSocket) -> None:
        self._sockets.discard(socket)
        socket.deleteLater()
