// data/inputs/test.c
#include <stdio.h>

void process_data(int *arr, int len) {
    for (int i = 0; i < len; i++) {
        *(arr + i) = *(arr + i) * 2; // 포인터 연산 (unsafe 유발 포인트)
    }
}

int main() {
    int data[3] = {1, 2, 3};
    process_data(data, 3);
    return 0;
}
