/**
 * Base class for shapes
 */
class Shape {
    constructor(name) {
        this.name = name;
    }

    area() {
        return 0;
    }
}

class Circle extends Shape {
    constructor(radius) {
        super(radius);
        this.radius = radius;
    }

    area() {
        return Math.PI * this.radius * this.radius;
    }
}

function calculateTotal(shapes) {
    let total = 0;
    for (const shape of shapes) {
        total += shape.area();
    }
    return total;
}
