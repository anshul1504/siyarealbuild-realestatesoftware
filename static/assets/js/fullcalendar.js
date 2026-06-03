if(jQuery('#eventStartDate').length > 0 ){
	$("#eventStartDate").flatpickr({
		enableTime: true,
		dateFormat: "Y-m-d H:i",
	});
}
if(jQuery('#eventEndDate').length > 0 ){
	$("#eventEndDate").flatpickr({
		enableTime: true,
		dateFormat: "Y-m-d H:i",
	});
}
document.addEventListener('DOMContentLoaded', function () {
    const Draggable = FullCalendar.Draggable;

    new Draggable(document.getElementById('external-events'), {
        itemSelector: '.fc-event',
        eventData: function (eventEl) {
            return {
                title: eventEl.innerText.trim(),
                backgroundColor: eventEl.getAttribute('data-color'),
                borderColor: eventEl.getAttribute('data-color'),
                textColor: '#fff',
                extendedProps: {
                    label: eventEl.getAttribute('data-label') || '',
                    location: eventEl.getAttribute('data-location') || '',
                    description: eventEl.getAttribute('data-description') || ''
                }
            };
        }
    });

    const calendarEl = document.getElementById('calendar');
    const calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        editable: true,
        droppable: true,
        headerToolbar: {
            left: 'prev,next today',
            center: 'title',
            right: 'dayGridMonth,timeGridWeek,timeGridDay'
        },

        eventReceive: function (info) {
            // Add default end = start + 1 day if end is missing
            if (!info.event.end) {
                const end = new Date(info.event.start);
                end.setDate(end.getDate() + 1); // +1 day
                info.event.setEnd(end);
            }
        },

        eventClick: function (info) {
            info.jsEvent.preventDefault();
            document.getElementById('eventTitle').textContent = info.event.title;
            document.getElementById('eventStart').textContent = info.event.start ? info.event.start.toLocaleString() : 'N/A';
            document.getElementById('eventEnd').textContent = info.event.end ? info.event.end.toLocaleString() : 'N/A';
            document.getElementById('eventLocation').textContent = info.event.extendedProps.location || 'N/A';
            document.getElementById('eventDescription').textContent = info.event.extendedProps.description || 'N/A';

            let eventModal = new bootstrap.Modal(document.getElementById('eventDetailsModal'));
            eventModal.show();
        }
    });

    calendar.render();

    document.getElementById('eventForm').addEventListener('submit', function (e) {
        e.preventDefault();

        const title = document.getElementById('title').value;
        const label = document.getElementById('label').value;
        const start = document.getElementById('eventStartDate').value;
        const end = document.getElementById('eventEndDate').value;
        const url = document.getElementById('url').value;
        const location = document.getElementById('location').value;
        const description = document.getElementById('description').value;

        if (title && start) {
            calendar.addEvent({
                title: label ? `${title}` : title,
                start: start,
                end: end || null,
                url: url || null,
                extendedProps: {
                    label: label || '',
                    location: location || '',
                    description: description || ''
                },
                backgroundColor: `var(--bs-${label})`,
                borderColor: '#fff',
                textColor: '#fff'
            });

            document.getElementById('eventForm').reset();
            document.getElementById('modalAddEvent').classList.remove('show');
            document.querySelector('.modal-backdrop').remove();
            document.body.classList.remove('modal-open');
            document.body.style = '';
        } else {
            alert('Please enter required fields.');
        }
    });
});