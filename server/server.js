// server.js
import express from "express";
import http from "http";
import path from "path";
import { Server } from "socket.io";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const server = http.createServer(app);

const io = new Server(server, {
  cors: {
    origin: "*",
    methods: ["GET", "POST"],
  },
});

app.use(express.static(path.join(__dirname, "rtc-lap")));

io.on("connection", (socket) => {
  console.log("🔌 user connected");

  socket.on("join", (room) => {
    const clients = io.sockets.adapter.rooms.get(room);
    const numClients = clients ? clients.size : 0;

    console.log(`📌 user join room: ${room}, hiện có ${numClients} client`);

    if (numClients === 0) {
      socket.join(room);
      socket.emit("created");
    } else if (numClients === 1) {
      socket.join(room);
      socket.emit("joined");
      socket.to(room).emit("ready");
    } else {
      socket.emit("full"); // phòng đã đủ (chỉ 2 người)
    }
  });

  socket.on("offer", ({ room, desc }) => {
    console.log("📡 offer gửi đến room:", room);
    socket.to(room).emit("offer", desc);
  });

  socket.on("answer", ({ room, desc }) => {
    console.log("📡 answer gửi đến room:", room);
    socket.to(room).emit("answer", desc);
  });

  socket.on("candidate", ({ room, candidate }) => {
    console.log("📡 candidate gửi đến room:", room);
    socket.to(room).emit("candidate", candidate);
  });

  socket.on("disconnect", () => {
    console.log("❌ user disconnected");
  });
});

const PORT = 3000;
server.listen(PORT, () => {
  console.log(`🚀 Server running at http://localhost:${PORT}`);
});
