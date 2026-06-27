using Microsoft.EntityFrameworkCore;
using NewsMarketAgent.Api.Data;
using NewsMarketAgent.Api.Models;

namespace NewsMarketAgent.Api.Services;

public interface ISignalService
{
    Task<IEnumerable<SignalResponseDto>> GetAsync(string? ticker, int limit, string? from);
    Task<SignalResponseDto?>             GetByIdAsync(Guid id);
    Task                                 ProcessCallbackAsync(SignalCallbackDto dto);
}

public class SignalService(AppDbContext db, ILogger<SignalService> log) : ISignalService
{
    public async Task<IEnumerable<SignalResponseDto>> GetAsync(
        string? ticker, int limit, string? from)
    {
        var query = db.Signals
            .Where(s => s.GovernancePassed)
            .AsQueryable();

        if (!string.IsNullOrEmpty(ticker))
            query = query.Where(s => s.Ticker == ticker);

        if (!string.IsNullOrEmpty(from) && DateTime.TryParse(from, out var fromDate))
            query = query.Where(s => s.PublishedAt >= fromDate);

        return await query
            .OrderByDescending(s => s.PublishedAt)
            .Take(limit)
            .Select(s => ToDto(s))
            .ToListAsync();
    }

    public async Task<SignalResponseDto?> GetByIdAsync(Guid id)
    {
        var s = await db.Signals
            .FirstOrDefaultAsync(s => s.Id == id && s.GovernancePassed);
        return s is null ? null : ToDto(s);
    }

    public async Task ProcessCallbackAsync(SignalCallbackDto dto)
    {
        await db.NewsArticles
            .Where(a => a.Id == dto.ArticleId)
            .ExecuteUpdateAsync(s => s.SetProperty(a => a.Processed, true));

        if (!dto.GovernancePassed || dto.Signal is null)
        {
            log.LogInformation("Signal rejected for article {Id}: {Reason}",
                               dto.ArticleId, dto.RejectionReason);
            return;
        }

        if (!PassesApiGovernance(dto.Signal))
        {
            log.LogWarning("Signal failed C# governance check for article {Id}",
                           dto.ArticleId);
            return;
        }

        db.Signals.Add(new Signal
        {
            Ticker                = dto.Ticker,
            ArticleId             = dto.ArticleId,
            EventType             = dto.Signal.EventType,
            Sentiment             = dto.Signal.Sentiment,
            Confidence            = dto.Signal.Confidence,
            ImpactSummary         = dto.Signal.ImpactSummary,
            TimeHorizon           = dto.Signal.TimeHorizon,
            SourceCitations       = dto.Signal.SourceCitations,
            UncertaintyFactors    = dto.Signal.UncertaintyFactors,
            Disclaimer            = dto.Signal.Disclaimer,
            GovernancePassed      = true,
            SourceCredibilityTier = dto.Signal.SourceCredibilityTier,
            AlertSuppressed       = dto.Signal.AlertSuppressed,
            RequiresHumanReview   = dto.Signal.RequiresHumanReview,
            GovernanceWarnings    = dto.Signal.GovernanceWarnings,
            PublishedAt           = DateTime.UtcNow,
        });
        await db.SaveChangesAsync();
    }

    private static bool PassesApiGovernance(SignalPayloadDto s)
    {
        if (string.IsNullOrEmpty(s.Disclaimer)) return false;
        if (s.Confidence < 0.65m) return false;
        string[] prohibited = ["buy", "sell", "invest", "guaranteed", "price target"];
        return !prohibited.Any(p =>
            s.ImpactSummary.Contains(p, StringComparison.OrdinalIgnoreCase));
    }

    private static SignalResponseDto ToDto(Signal s) => new()
    {
        Id                    = s.Id.ToString(),
        Ticker                = s.Ticker,
        EventType             = s.EventType,
        Sentiment             = s.Sentiment,
        Confidence            = s.Confidence,
        ImpactSummary         = s.ImpactSummary,
        TimeHorizon           = s.TimeHorizon,
        SourceCitations       = s.SourceCitations,
        UncertaintyFactors    = s.UncertaintyFactors,
        Disclaimer            = s.Disclaimer,
        PublishedAt           = s.PublishedAt,
        GovernancePassed      = s.GovernancePassed,
        SourceCredibilityTier = s.SourceCredibilityTier,
        GovernanceWarnings    = s.GovernanceWarnings,
    };
}
