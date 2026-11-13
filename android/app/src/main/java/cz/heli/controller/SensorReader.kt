package cz.heli.controller

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin

/**
 * Čte natočení telefonu ze senzorů a převádí ho na osy -1..1.
 *
 * Používá GAME_ROTATION_VECTOR (gyroskop + akcelerometr, bez magnetometru),
 * takže se nerozhazuje magnetickým rušením v autě/stole a nedělá skoky.
 */
class SensorReader(context: Context) : SensorEventListener {

    private val sm = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val sensor: Sensor? =
        sm.getDefaultSensor(Sensor.TYPE_GAME_ROTATION_VECTOR)
            ?: sm.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)

    private val rot = FloatArray(9)
    private val ori = FloatArray(3)

    // Poslední surové úhly (rad) a referenční střed (nastaví tlačítko "Střed").
    private var rawPitch = 0f
    private var rawRoll = 0f
    private var rawYaw = 0f
    private var centerPitch = 0f
    private var centerRoll = 0f
    private var centerYaw = 0f

    // Výsledné osy -1..1, čte je odesílací vlákno.
    @Volatile
    var pitch = 0f
        private set

    @Volatile
    var roll = 0f
        private set

    @Volatile
    var yaw = 0f
        private set

    /** Úhel, při kterém je výchylka plná (~35°). Čím menší, tím citlivější. */
    private val maxTilt = Math.toRadians(35.0).toFloat()
    /** Úhel otočení na plnou výchylku pedálů (~45°). */
    private val maxYaw = Math.toRadians(45.0).toFloat()

    /** Vyhlazení (0..1): menší = plynulejší, ale pomalejší reakce. */
    private val alpha = 0.6f
    private var sPitch = 0f
    private var sRoll = 0f
    private var sYaw = 0f

    val available: Boolean get() = sensor != null

    fun start() {
        sensor?.let { sm.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME) }
    }

    fun stop() {
        sm.unregisterListener(this)
    }

    /** Aktuální poloha telefonu se stane středem (nulová výchylka). */
    fun recenter() {
        centerPitch = rawPitch
        centerRoll = rawRoll
        centerYaw = rawYaw
    }

    override fun onSensorChanged(event: SensorEvent) {
        SensorManager.getRotationMatrixFromVector(rot, event.values)
        SensorManager.getOrientation(rot, ori) // ori[0]=azimut, ori[1]=pitch, ori[2]=roll

        rawYaw = ori[0]
        rawPitch = ori[1]
        rawRoll = ori[2]

        val dPitch = rawPitch - centerPitch
        val dRoll = rawRoll - centerRoll
        val dYaw = wrap(rawYaw - centerYaw)

        // Vyhlazení a normalizace na -1..1
        sPitch = alpha * dPitch + (1 - alpha) * sPitch
        sRoll = alpha * dRoll + (1 - alpha) * sRoll
        sYaw = alpha * dYaw + (1 - alpha) * sYaw

        pitch = clamp(sPitch / maxTilt)
        roll = clamp(sRoll / maxTilt)
        yaw = clamp(sYaw / maxYaw)
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    private fun wrap(a: Float): Float = atan2(sin(a.toDouble()), cos(a.toDouble())).toFloat()

    private fun clamp(v: Float) = v.coerceIn(-1f, 1f)
}
