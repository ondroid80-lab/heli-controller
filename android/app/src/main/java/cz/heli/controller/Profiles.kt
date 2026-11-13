package cz.heli.controller

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/** Tlačítko na obrazovce. [bit] je index bitu (0..7) a musí odpovídat config.json na PC. */
data class ButtonDef(val label: String, val bit: Int)

/** Profil = sada tlačítek a citlivost osy pro jednu hru nebo stroj. */
data class Profile(
    val name: String,
    val buttons: List<ButtonDef>,
    val pitchScale: Float = 1f,
    val rollScale: Float = 1f,
    val yawScale: Float = 1f,
)

/**
 * Ukládání profilů jako JSON do SharedPreferences.
 * Úpravu lze dělat přímo v aplikaci (tlačítko "Profily") jako text JSON.
 */
object ProfileStore {
    private const val PREFS = "heli_prefs"
    private const val KEY = "profiles_json"

    fun defaults(): List<Profile> = listOf(
        Profile(
            name = "Arma 3 / Wardogs",
            buttons = listOf(
                ButtonDef("Start", 6),
                ButtonDef("Světla", 4),
                ButtonDef("Kamera", 5),
                ButtonDef("Palba", 0),
                ButtonDef("Flares", 1),
                ButtonDef("Zbraň", 2),
                ButtonDef("Menu", 7),
                ButtonDef("Y", 3),
            ),
        ),
        Profile(
            name = "Test",
            buttons = listOf(ButtonDef("A", 0), ButtonDef("B", 1)),
            pitchScale = 0.7f,
            rollScale = 0.7f,
            yawScale = 0.7f,
        ),
    )

    fun load(ctx: Context): MutableList<Profile> {
        val raw = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY, null) ?: return defaults().toMutableList()
        return try {
            fromJson(raw).toMutableList()
        } catch (e: Exception) {
            defaults().toMutableList()
        }
    }

    fun save(ctx: Context, profiles: List<Profile>) {
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY, toJson(profiles))
            .apply()
    }

    fun toJson(profiles: List<Profile>): String {
        val arr = JSONArray()
        for (p in profiles) {
            val buttons = JSONArray()
            for (b in p.buttons) {
                buttons.put(JSONObject().put("label", b.label).put("bit", b.bit))
            }
            arr.put(
                JSONObject()
                    .put("name", p.name)
                    .put("pitchScale", p.pitchScale.toDouble())
                    .put("rollScale", p.rollScale.toDouble())
                    .put("yawScale", p.yawScale.toDouble())
                    .put("buttons", buttons)
            )
        }
        return arr.toString(2)
    }

    /** Vyhodí výjimku, pokud JSON není platný nebo má bit mimo rozsah 0..7. */
    fun fromJson(raw: String): List<Profile> {
        val arr = JSONArray(raw)
        val out = mutableListOf<Profile>()
        for (i in 0 until arr.length()) {
            val o = arr.getJSONObject(i)
            val btnArr = o.getJSONArray("buttons")
            val buttons = mutableListOf<ButtonDef>()
            for (j in 0 until btnArr.length()) {
                val b = btnArr.getJSONObject(j)
                val bit = b.getInt("bit")
                require(bit in 0..7) { "Bit musí být 0 až 7, je $bit" }
                buttons.add(ButtonDef(b.getString("label"), bit))
            }
            out.add(
                Profile(
                    name = o.getString("name"),
                    buttons = buttons,
                    pitchScale = o.optDouble("pitchScale", 1.0).toFloat(),
                    rollScale = o.optDouble("rollScale", 1.0).toFloat(),
                    yawScale = o.optDouble("yawScale", 1.0).toFloat(),
                )
            )
        }
        require(out.isNotEmpty()) { "Musí být alespoň jeden profil" }
        return out
    }
}
