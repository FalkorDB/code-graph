package test-project;

public class c {
    
    private int a;
    
    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }

    public static void print() {
        System.out.println("Hello, World!");
    }

    public int getA() {
        return a;
    }   

    public void setA(int a) {
        this.a = a;
    }

    public void inc() {
        setA(getA() + 1);
    }
}
