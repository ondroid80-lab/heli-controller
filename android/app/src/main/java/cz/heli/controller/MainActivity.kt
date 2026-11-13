package cz.heli.controller

import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.os.Bundle
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast

class MainActivity : Activity() {

    private lateinit var profiles: MutableList<Profile>
    private var current = 0

    private lateinit var sensors: SensorReader
    private lateinit var sender: UdpSender

    private var buttonMask = 0
    private var collective = 0f

    private lateinit var ipField: EditText
    private lateinit var connectBtn: Button
    private lateinit var statusView: TextView
    private lateinit var profileSpinner: Spinner
    private lateinit var buttonArea: LinearLayout
    private lateinit var collectiveBar: SeekBar

    private val prefs by lazy { getSharedPreferences("heli_prefs", Context.MODE_PRIVATE) }

    private fun profile(): Profile = profiles[current]

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        profiles = ProfileStore.load(this)
        sensors = SensorReader(this)

        // Odesílací vlákno si každých 20 ms vyzvedne aktuální stav a aplikuje citlivost profilu.
        sender = UdpSender {
            val p = profile()
            Input(
                pitch = sensors.pitch * p.pitchScale,
                roll = sensors.roll * p.rollScale,
                yaw = sensors.yaw * p.yawScale,
                collective = collective,
                buttons = buttonMask,
            )
        }
        sender.onStatus = { msg -> runOnUiThread { statusView.text = msg; updateConnectButton() } }

        buildUi()
        if (!sensors.available) {
            statusView.text = "Tento telefon nemá senzor natočení."
        }
    }

    override fun onResume() {
        super.onResume()
        sensors.start()
    }

    override fun onPause() {
        super.onPause()
        sensors.stop()
        sender.stop()
        buttonMask = 0
        collective = 0f
    }

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 16, 24, 16)
        }

        // Horní řádek: IP PC + připojení
        val top = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        ipField = EditText(this).apply {
            hint = "IP adresa PC (např. 192.168.0.10)"
            setText(prefs.getString("ip", "192.168.0.10"))
            setSingleLine(true)
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        }
        connectBtn = Button(this).apply {
            text = "Připojit"
            setOnClickListener { toggleConnection() }
        }
        val findBtn = Button(this).apply {
            text = "Najít PC"
            setOnClickListener { findPc() }
        }
        top.addView(ipField)
        top.addView(findBtn)
        top.addView(connectBtn)
        root.addView(top)

        // Výběr profilu
        profileSpinner = Spinner(this).apply {
            adapter = ArrayAdapter(
                this@MainActivity,
                android.R.layout.simple_spinner_dropdown_item,
                profiles.map { it.name },
            )
            setSelection(current)
            onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                override fun onItemSelected(parent: AdapterView<*>?, view: View?, pos: Int, id: Long) {
                    if (pos != current) {
                        current = pos
                        rebuildButtons()
                    }
                }
                override fun onNothingSelected(parent: AdapterView<*>?) {}
            }
        }
        root.addView(profileSpinner)

        statusView = TextView(this).apply {
            text = "Odpojeno"
            textSize = 14f
            setPadding(0, 8, 0, 8)
        }
        root.addView(statusView)

        // Hlavní oblast: tlačítka vlevo, kolektiv dole
        buttonArea = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f)
        }
        root.addView(buttonArea)

        collectiveBar = SeekBar(this).apply {
            max = 200
            progress = 100 // střed = 0
            setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(bar: SeekBar?, progress: Int, fromUser: Boolean) {
                    collective = (progress - 100) / 100f
                }
                override fun onStartTrackingTouch(bar: SeekBar?) {}
                override fun onStopTrackingTouch(bar: SeekBar?) {}
            })
        }
        root.addView(TextView(this).apply { text = "Kolektiv (nahoru = zvedání, dolů = klesání)" })
        root.addView(collectiveBar)

        // Spodní řádek
        val bottom = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        bottom.addView(Button(this).apply {
            text = "Střed"
            setOnClickListener {
                sensors.recenter()
                collectiveBar.progress = 100
                Toast.makeText(this@MainActivity, "Střed nastaven", Toast.LENGTH_SHORT).show()
            }
        })
        bottom.addView(Button(this).apply {
            text = "Profily"
            setOnClickListener { editProfiles() }
        })
        root.addView(bottom)

        setContentView(ScrollView(this).apply { addView(root) })
        rebuildButtons()

        // První spuštění bez uložené IP: PC najdeme automaticky.
        if (!prefs.contains("ip")) findPc()
    }

    /** Vytvoří tlačítka podle aktuálního profilu (4 na řádek). */
    private fun rebuildButtons() {
        buttonArea.removeAllViews()
        buttonMask = 0
        val defs = profile().buttons
        var row: LinearLayout? = null
        defs.forEachIndexed { i, def ->
            if (i % 4 == 0) {
                row = LinearLayout(this).apply {
                    orientation = LinearLayout.HORIZONTAL
                    layoutParams = LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f
                    )
                }
                buttonArea.addView(row)
            }
            val mask = 1 shl def.bit
            val btn = Button(this).apply {
                text = def.label
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f)
                setOnTouchListener { v, e ->
                    when (e.actionMasked) {
                        MotionEvent.ACTION_DOWN, MotionEvent.ACTION_POINTER_DOWN -> {
                            buttonMask = buttonMask or mask
                            v.isPressed = true
                        }
                        MotionEvent.ACTION_UP, MotionEvent.ACTION_POINTER_UP, MotionEvent.ACTION_CANCEL -> {
                            buttonMask = buttonMask and mask.inv()
                            v.isPressed = false
                        }
                    }
                    true
                }
            }
            row?.addView(btn)
        }
    }

    /** Hledá PC v síti. Při jednom nálezu rovnou vyplní IP, při více nabídne výběr. */
    private fun findPc() {
        statusView.text = "Hledám PC v síti…"
        Thread {
            val found = UdpSender.discover()
            runOnUiThread {
                when (found.size) {
                    0 -> statusView.text = "PC nenalezeno. Je spuštěný Heli Controller a telefon je ve stejné Wi-Fi?"
                    1 -> {
                        ipField.setText(found[0].first)
                        statusView.text = "Nalezeno: ${found[0].second} (${found[0].first})"
                    }
                    else -> AlertDialog.Builder(this)
                        .setTitle("Vyber PC")
                        .setItems(found.map { "${it.second} (${it.first})" }.toTypedArray()) { _, i ->
                            ipField.setText(found[i].first)
                            statusView.text = "Vybráno: ${found[i].second}"
                        }
                        .show()
                }
            }
        }.start()
    }

    private fun toggleConnection() {
        if (sender.isRunning) {
            sender.stop()
        } else {
            val ip = ipField.text.toString().trim()
            prefs.edit().putString("ip", ip).apply()
            sender.start(ip)
        }
        updateConnectButton()
    }

    private fun updateConnectButton() {
        connectBtn.text = if (sender.isRunning) "Odpojit" else "Připojit"
    }

    /** Úprava profilů jako JSON text (jednoduchý editor pro MVP). */
    private fun editProfiles() {
        val input = EditText(this).apply {
            setText(ProfileStore.toJson(profiles))
            setSingleLine(false)
            minLines = 12
            textSize = 12f
        }
        AlertDialog.Builder(this)
            .setTitle("Profily (JSON)")
            .setView(ScrollView(this).apply { addView(input) })
            .setPositiveButton("Uložit") { _, _ ->
                try {
                    val parsed = ProfileStore.fromJson(input.text.toString())
                    profiles = parsed.toMutableList()
                    ProfileStore.save(this, profiles)
                    current = 0
                    profileSpinner.adapter = ArrayAdapter(
                        this, android.R.layout.simple_spinner_dropdown_item, profiles.map { it.name }
                    )
                    rebuildButtons()
                    Toast.makeText(this, "Profily uloženy", Toast.LENGTH_SHORT).show()
                } catch (e: Exception) {
                    Toast.makeText(this, "Chybný JSON: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
            .setNegativeButton("Zrušit", null)
            .show()
    }
}
