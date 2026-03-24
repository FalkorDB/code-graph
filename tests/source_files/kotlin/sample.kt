/**
 * A base interface for logging
 */
interface Logger {
    fun log(message: String)
}

/**
 * Base class for shapes
 */
open class Shape(val name: String) {
    open fun area(): Double = 0.0
}

class Circle(val radius: Double) : Shape("circle"), Logger {
    override fun area(): Double {
        return Math.PI * radius * radius
    }

    override fun log(message: String) {
        println(message)
    }
}

fun calculateTotal(shapes: List<Shape>): Double {
    var total = 0.0
    for (shape in shapes) {
        total += shape.area()
    }
    return total
}

object AppConfig : Logger {
    val version = "1.0"

    override fun log(message: String) {
        println("[$version] $message")
    }
}
