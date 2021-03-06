# subscribe simple generator
import time


def generator(n):
    for i in range(n):
        yield i * 2


def call_generator(num, iteration):
    item = 0
    for t in range(iteration):
        num += t % 5
        for i in generator(num):
            item = i + item % 5

    return item


def measure():
    print("Start timing...")
    start = time.time()

    num = 1000
    last_item = call_generator(num, 10000)  # 1000000

    print("Last item ", last_item)

    duration = "%.3f\n" % (time.time() - start)
    print("generator: " + duration)


# warm up
print('warming up ...')
for run in range(2000):
    call_generator(100, 100)

measure()
