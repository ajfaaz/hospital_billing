class Room(models.Model):
    ROOM_TYPES = [('General', 'General'), ('Private', 'Private'), ('ICU', 'ICU')]
    room_number = models.CharField(max_length=10, unique=True)
    room_type = models.CharField(max_length=20, choices=ROOM_TYPES)
    price_per_day = models.DecimalField(max_digits=8, decimal_places=2)

class Bed(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    bed_number = models.CharField(max_length=10)
    is_occupied = models.BooleanField(default=False)

class Admission(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    bed = models.ForeignKey(Bed, on_delete=models.CASCADE)
    check_in = models.DateTimeField()
    check_out = models.DateTimeField(null=True, blank=True)

    def stay_duration(self):
        if self.check_out:
            return (self.check_out - self.check_in).days or 1
        return 0
