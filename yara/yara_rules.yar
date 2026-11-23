import "hash"

rule Lab_Payload_ELF
{
    meta:
        description = "Lab payload.elf (ELF32 x86, static)"
        hash = "6f28905a9fd83239f30f9842ff57405eae83246884a7bd090b544bde59fb6d89"
    condition:
        hash.sha256(0, filesize) == "6f28905a9fd83239f30f9842ff57405eae83246884a7bd090b544bde59fb6d89"
}
