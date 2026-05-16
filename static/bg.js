(function () {

    document.addEventListener('DOMContentLoaded', () => {

        const canvas = document.createElement('canvas');
        canvas.id = 'bgCanvas';
        canvas.style.cssText = `
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            z-index: 0;
            pointer-events: none;
            display: block;
        `;

        document.body.insertBefore(canvas, document.body.firstChild);


    const ctx = canvas.getContext('2d');
    const COLS = 26, ROWS = 17;
    let nodes = [], t = 0;

    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        init();
    }

    function init() {
        nodes = [];
        const sx = canvas.width / COLS;
        const sy = canvas.height / ROWS;
        for (let r = 0; r <= ROWS; r++) {
            for (let c = 0; c <= COLS; c++) {
                nodes.push({
                    ox: c * sx, oy: r * sy,
                    x: 0, y: 0,
                    phase: Math.random() * Math.PI * 2,
                    speed: 0.15 + Math.random() * 0.2,
                    amp: 2 + Math.random() * 4,
                    op: 0.03 + Math.random() * 0.05
                });
            }
        }
    }

    function draw() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        t += 0.004;

        nodes.forEach(n => {
            n.x = n.ox + Math.sin(t * n.speed + n.phase) * n.amp;
            n.y = n.oy + Math.cos(t * n.speed * 0.7 + n.phase) * n.amp * 0.6;
        });

        const C = COLS + 1;
        for (let r = 0; r <= ROWS; r++) {
            for (let c = 0; c <= COLS; c++) {
                const i = r * C + c;
                const n = nodes[i];

                if (c < COLS) {
                    const n2 = nodes[i + 1];
                    ctx.beginPath();
                    ctx.moveTo(n.x, n.y);
                    ctx.lineTo(n2.x, n2.y);
                    ctx.strokeStyle = `rgba(255,255,255,${(n.op + n2.op) / 2})`;
                    ctx.lineWidth = 0.4;
                    ctx.stroke();
                }

                if (r < ROWS) {
                    const n2 = nodes[(r + 1) * C + c];
                    ctx.beginPath();
                    ctx.moveTo(n.x, n.y);
                    ctx.lineTo(n2.x, n2.y);
                    ctx.strokeStyle = `rgba(255,255,255,${(n.op + n2.op) / 2})`;
                    ctx.lineWidth = 0.4;
                    ctx.stroke();
                }

                ctx.beginPath();
                ctx.arc(n.x, n.y, 0.7, 0, Math.PI * 2);
                ctx.fillStyle = `rgba(255,255,255,${n.op * 1.5})`;
                ctx.fill();
            }
        }

        // Full black overlay dulu
        ctx.fillStyle = 'rgba(8,8,8,0.55)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Vignette tambahan di pinggir
        const gx = canvas.width / 2;
        const gy = canvas.height / 2;
        const gr = ctx.createRadialGradient(gx, gy, 0, gx, gy, Math.max(gx, gy));
        gr.addColorStop(0,    'rgba(8,8,8,0)');
        gr.addColorStop(0.6,  'rgba(8,8,8,0)');
        gr.addColorStop(1,    'rgba(8,8,8,0.9)');
        ctx.fillStyle = gr;
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        requestAnimationFrame(draw);
    }

    resize();
    draw();
    window.addEventListener('resize', resize);
    });
})();