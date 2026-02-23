import random


def generate_cipher_report():
    random.seed(42)
    original_numbers = [random.randint(10, 50) for _ in range(15)]

    refined_list = []
    for i in range(1, len(original_numbers) - 1):
        if (original_numbers[i - 1] + original_numbers[i + 1]) % 2 == 0:
            refined_list.append(original_numbers[i] * 2)
        else:
            refined_list.append(original_numbers[i])

    total_sum = sum(refined_list)

    return (
        f"First five original numbers: {original_numbers[:5]}\n"
        f"Refined list: {refined_list}\n"
        f"Total sum of refined list: {total_sum}"
    )


# Example usage:
print(generate_cipher_report())