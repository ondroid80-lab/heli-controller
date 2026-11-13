package cz.heli.controller

import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress

/** Jeden stav ovladače, který se posílá na PC. */
data class Input(
    val pitch: Float,
    val roll: Float,
    val yaw: Float,
    val collective: Float,
    val buttons: Int,
)

/**
 * Posílá stav ovladače na PC přes UDP ~50× za sekundu.
 * Stav bere z funkce [provider], takže vlákno vždy pošle aktuální hodnoty.
 */
class UdpSender(private val provider: () -> Input) {

    companion object {
        const val PORT = 47800
        private const val INTERVAL_MS = 20L
        private const val DISCOVER = "HELI_DISCOVER"

        /** Najde PC s běžícím přijímačem. Vrací seznam (IP, jméno PC). Volat mimo hlavní vlákno. */
        fun discover(timeoutMs: Int = 1500): List<Pair<String, String>> {
            val found = LinkedHashMap<String, String>()
            DatagramSocket().use { s ->
                s.broadcast = true
                s.soTimeout = 300
                val msg = DISCOVER.toByteArray(Charsets.UTF_8)
                s.send(DatagramPacket(msg, msg.size, InetAddress.getByName("255.255.255.255"), PORT))

                val buf = ByteArray(512)
                val end = System.currentTimeMillis() + timeoutMs
                while (System.currentTimeMillis() < end) {
                    try {
                        val p = DatagramPacket(buf, buf.size)
                        s.receive(p)
                        val json = JSONObject(String(p.data, 0, p.length, Charsets.UTF_8))
                        if (json.optInt("heli") == 1) {
                            found[p.address.hostAddress ?: continue] = json.optString("name", "PC")
                        }
                    } catch (_: java.net.SocketTimeoutException) {
                        // nic nepřišlo, zkusíme znovu do konce času
                    } catch (_: org.json.JSONException) {
                        // cizí paket na stejném portu, ignorovat
                    }
                }
            }
            return found.map { (ip, name) -> ip to name }
        }
    }

    @Volatile private var running = false
    private var thread: Thread? = null

    /** Stavová hlášení pro UI (volá se z jiného vlákna). */
    var onStatus: ((String) -> Unit)? = null

    val isRunning: Boolean get() = running

    fun start(host: String) {
        if (running) return
        running = true
        thread = Thread({ loop(host) }, "udp-sender").apply { isDaemon = true; start() }
    }

    fun stop() {
        running = false
        thread?.join(200)
        thread = null
        onStatus?.invoke("Odpojeno")
    }

    private fun loop(host: String) {
        val socket: DatagramSocket
        val address: InetAddress
        try {
            address = InetAddress.getByName(host)
            socket = DatagramSocket()
        } catch (e: Exception) {
            running = false
            onStatus?.invoke("Chyba: ${e.message ?: "neplatná IP adresa"}")
            return
        }

        onStatus?.invoke("Připojeno k $host:$PORT")
        try {
            while (running) {
                val s = provider()
                val json = JSONObject()
                    .put("pitch", s.pitch.toDouble())
                    .put("roll", s.roll.toDouble())
                    .put("yaw", s.yaw.toDouble())
                    .put("collective", s.collective.toDouble())
                    .put("buttons", s.buttons)
                    .toString()
                val bytes = json.toByteArray(Charsets.UTF_8)
                socket.send(DatagramPacket(bytes, bytes.size, address, PORT))
                Thread.sleep(INTERVAL_MS)
            }
        } catch (e: Exception) {
            running = false
            onStatus?.invoke("Chyba odesílání: ${e.message}")
        } finally {
            socket.close()
        }
    }
}
