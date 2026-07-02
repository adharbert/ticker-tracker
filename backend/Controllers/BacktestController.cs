using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using NewsMarketAgent.Api.Data;
using NewsMarketAgent.Api.Models;
using NewsMarketAgent.Api.Services;

namespace NewsMarketAgent.Api.Controllers;

[ApiController]
[Route("api/backtest")]
public class BacktestController(AppDbContext db, IBacktestTriggerService backtestTrigger) : ControllerBase
{
    [HttpPost("trigger")]
    public async Task<IActionResult> Trigger()
    {
        var status = await backtestTrigger.RecomputeAsync();
        return Ok(new { status });
    }

    [HttpGet("{ticker}")]
    public async Task<ActionResult<BacktestResponseDto>> GetByTicker(string ticker)
    {
        var result = await db.BacktestResults
            .Where(r => r.Ticker == ticker.ToUpper())
            .OrderByDescending(r => r.ComputedAt)
            .FirstOrDefaultAsync();

        if (result is null)
            return NotFound(new { message = $"No backtest data for {ticker.ToUpper()}. Run python -m scripts.backtest first." });

        return ToDto(result);
    }

    [HttpGet]
    public async Task<IEnumerable<BacktestResponseDto>> GetAll()
    {
        var latest = await db.BacktestResults
            .GroupBy(r => r.Ticker)
            .Select(g => g.OrderByDescending(r => r.ComputedAt).First())
            .ToListAsync();

        return latest.OrderByDescending(r => r.SampleSize).Select(ToDto);
    }

    private static BacktestResponseDto ToDto(BacktestResult r) => new()
    {
        Ticker           = r.Ticker,
        LookAheadDays    = r.LookAheadDays,
        SampleSize       = r.SampleSize,
        Accuracy         = r.Accuracy,
        AccuracyNote     = r.AccuracyNote,
        BaselineAccuracy = r.BaselineAccuracy,
        VsBaseline       = r.VsBaseline,
        Disclaimer       = r.Disclaimer,
        ComputedAt       = r.ComputedAt,
    };
}
