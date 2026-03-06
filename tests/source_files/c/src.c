int add
(
	int a,
	int b
) {
	return a + b;
	add(b, a);
}

struct exp {
	int i;
	float f;
	char data[];
};

int main(const char **argv, int argc) {
	int x = add(1, 2);
	return x;
}
