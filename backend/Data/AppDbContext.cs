using Microsoft.EntityFrameworkCore;
using NewsMarketAgent.Api.Models;

namespace NewsMarketAgent.Api.Data;

public class AppDbContext(DbContextOptions<AppDbContext> options) : DbContext(options)
{
    public DbSet<WatchlistItem> Watchlist       { get; set; }
    public DbSet<NewsArticle>   NewsArticles    { get; set; }
    public DbSet<Signal>        Signals         { get; set; }
    public DbSet<Price>         Prices          { get; set; }
    public DbSet<BacktestResult> BacktestResults { get; set; }

    protected override void OnModelCreating(ModelBuilder m)
    {
        m.Entity<WatchlistItem>(e =>
        {
            e.ToTable("watchlist");
            e.HasKey(x => x.Ticker);
            e.Property(x => x.Ticker).HasColumnName("ticker");
            e.Property(x => x.Name).HasColumnName("name");
            e.Property(x => x.AddedAt).HasColumnName("added_at");
        });

        m.Entity<NewsArticle>(e =>
        {
            e.ToTable("news_articles");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id");
            e.Property(x => x.Ticker).HasColumnName("ticker");
            e.Property(x => x.Headline).HasColumnName("headline");
            e.Property(x => x.Body).HasColumnName("body");
            e.Property(x => x.SourceUrl).HasColumnName("source_url");
            e.Property(x => x.SourceName).HasColumnName("source_name");
            e.Property(x => x.DedupKey).HasColumnName("dedup_key");
            e.Property(x => x.EventType).HasColumnName("event_type");
            e.Property(x => x.PublishedAt).HasColumnName("published_at");
            e.Property(x => x.IngestedAt).HasColumnName("ingested_at");
            e.Property(x => x.Processed).HasColumnName("processed");
            e.HasIndex(x => x.DedupKey).IsUnique();
        });

        m.Entity<Signal>(e =>
        {
            e.ToTable("signals");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id");
            e.Property(x => x.Ticker).HasColumnName("ticker");
            e.Property(x => x.ArticleId).HasColumnName("article_id");
            e.Property(x => x.EventType).HasColumnName("event_type");
            e.Property(x => x.Sentiment).HasColumnName("sentiment");
            e.Property(x => x.Confidence).HasColumnName("confidence").HasPrecision(4, 3);
            e.Property(x => x.ImpactSummary).HasColumnName("impact_summary");
            e.Property(x => x.TimeHorizon).HasColumnName("time_horizon");
            e.Property(x => x.SourceCitations).HasColumnName("source_citations");
            e.Property(x => x.UncertaintyFactors).HasColumnName("uncertainty_factors");
            e.Property(x => x.Disclaimer).HasColumnName("disclaimer");
            e.Property(x => x.GovernancePassed).HasColumnName("governance_passed");
            e.Property(x => x.SourceCredibilityTier).HasColumnName("source_credibility_tier");
            e.Property(x => x.AlertSuppressed).HasColumnName("alert_suppressed");
            e.Property(x => x.RequiresHumanReview).HasColumnName("requires_human_review");
            e.Property(x => x.GovernanceWarnings).HasColumnName("governance_warnings");
            e.Property(x => x.PublishedAt).HasColumnName("published_at");
            e.Property(x => x.CreatedAt).HasColumnName("created_at");
        });

        m.Entity<Price>(e =>
        {
            e.ToTable("prices");
            e.HasKey(x => new { x.Ticker, x.Date });
            e.Property(x => x.Ticker).HasColumnName("ticker");
            e.Property(x => x.Date).HasColumnName("date");
            e.Property(x => x.Open).HasColumnName("open").HasPrecision(12, 4);
            e.Property(x => x.High).HasColumnName("high").HasPrecision(12, 4);
            e.Property(x => x.Low).HasColumnName("low").HasPrecision(12, 4);
            e.Property(x => x.Close).HasColumnName("close").HasPrecision(12, 4);
            e.Property(x => x.Volume).HasColumnName("volume");
        });

        m.Entity<BacktestResult>(e =>
        {
            e.ToTable("backtest_results");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id");
            e.Property(x => x.Ticker).HasColumnName("ticker");
            e.Property(x => x.EventType).HasColumnName("event_type");
            e.Property(x => x.LookAheadDays).HasColumnName("look_ahead_days");
            e.Property(x => x.SampleSize).HasColumnName("sample_size");
            e.Property(x => x.Accuracy).HasColumnName("accuracy").HasPrecision(5, 4);
            e.Property(x => x.AccuracyNote).HasColumnName("accuracy_note");
            e.Property(x => x.BaselineAccuracy).HasColumnName("baseline_accuracy").HasPrecision(5, 4);
            e.Property(x => x.VsBaseline).HasColumnName("vs_baseline").HasPrecision(5, 4);
            e.Property(x => x.Disclaimer).HasColumnName("disclaimer");
            e.Property(x => x.ComputedAt).HasColumnName("computed_at");
        });

        // Seed default watchlist
        m.Entity<WatchlistItem>().HasData(
            new WatchlistItem { Ticker = "BMRN", Name = "BioMarin Pharmaceutical Inc.",         AddedAt = new DateTime(2024, 1, 1, 0, 0, 0, DateTimeKind.Utc) },
            new WatchlistItem { Ticker = "NVDA", Name = "NVIDIA Corporation",                   AddedAt = new DateTime(2024, 1, 1, 0, 0, 0, DateTimeKind.Utc) },
            new WatchlistItem { Ticker = "C",    Name = "Citigroup Inc.",                       AddedAt = new DateTime(2024, 1, 1, 0, 0, 0, DateTimeKind.Utc) },
            new WatchlistItem { Ticker = "AMPH", Name = "Amphastar Pharmaceuticals Inc.",       AddedAt = new DateTime(2024, 1, 1, 0, 0, 0, DateTimeKind.Utc) },
            new WatchlistItem { Ticker = "DNLI", Name = "Denali Therapeutics Inc.",             AddedAt = new DateTime(2024, 1, 1, 0, 0, 0, DateTimeKind.Utc) },
            new WatchlistItem { Ticker = "SPCX", Name = "Space Exploration Technologies Corp.", AddedAt = new DateTime(2024, 1, 1, 0, 0, 0, DateTimeKind.Utc) }
        );
    }
}
