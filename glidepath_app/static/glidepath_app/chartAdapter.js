(function () {
    window.chartAdapter = {
        init: function (ctx, config) {
            return new Chart(ctx, config);
        },
        update: function (chart, config) {
            chart.config.data = config.data;
            if (config.options) {
                chart.config.options = config.options;
            }
            chart.update();
        },
        destroy: function (chart) {
            if (chart && typeof chart.destroy === 'function') {
                chart.destroy();
            }
        }
    };
})();
